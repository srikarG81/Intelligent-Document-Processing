# Deployment Guide

Let's deploy your invoice processing pipeline. This will take about 15 minutes.

## Architecture

```
┌─────────────┐
│   Client    │
│  Uploads    │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│   S3 Bucket         │
│  (Input Invoices)   │
└──────┬──────────────┘
       │ S3 Event Notification
       ▼
┌─────────────────────┐
│ Lambda:             │
│ InvoiceJobSubmitter │──────────┐
└─────────────────────┘          │
                                 │ Invokes BDA
                                 ▼
                       ┌─────────────────────┐
                       │  Bedrock Data       │
                       │  Automation (BDA)   │
                       └──────┬──────────────┘
                              │ Stores Results
                              ▼
                       ┌─────────────────────┐
                       │   S3 Bucket         │
                       │ (BDA Output JSON)   │
                       └──────┬──────────────┘
                              │
                              │ EventBridge Event
                              │ (Job Completed)
                              ▼
                       ┌─────────────────────┐
                       │   EventBridge       │
                       │   Rule              │
                       └──────┬──────────────┘
                              │ Triggers
                              ▼
                       ┌─────────────────────┐
                       │ Lambda:             │
                       │ ProcessBDAResults   │
                       └──────┬──────────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
         Confidence >= 70%          Confidence < 70%
                │                           │
                ▼                           ▼
        ┌───────────────┐         ┌──────────────────┐
        │   DynamoDB    │         │  Amazon A2I      │
        │   (invoices)  │         │  Human Review    │
        └───────────────┘         └──────────────────┘
```

## What We're Building

| Component | What It Does |
|-----------|-------------|
| **InvoiceJobSubmitter** | Submits BDA jobs when invoices arrive in S3 |
| **EventBridge Rule** | Catches BDA job completion events |
| **ProcessBDAResults** | Reads BDA output, routes by confidence |
| **DynamoDB Table** | Stores invoice data |
| **Amazon A2I** | Human review for low-confidence invoices (optional) |

---

## Before You Start

Make sure you have:

- ✅ AWS CLI configured
- ✅ DynamoDB table `invoices` (partition key: `invoice_id`)
- ✅ BDA project created with your invoice blueprint
- ✅ S3 bucket ready for invoices
- ⏸️ A2I Flow (optional - for human review)

---

## Step 1: Give Lambda Permission to Do Its Job

Your Lambda needs to read from S3, write to DynamoDB, and optionally invoke A2I.

### Create the IAM Policy

Save as `processbda-lambda-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Sid": "S3ReadBDAOutput",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR-BUCKET-NAME/*",
        "arn:aws:s3:::YOUR-BUCKET-NAME"
      ]
    },
    {
      "Sid": "DynamoDBWriteInvoices",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:519677643490:table/invoices"
    },
    {
      "Sid": "A2IHumanLoop",
      "Effect": "Allow",
      "Action": [
        "sagemaker:StartHumanLoop",
        "sagemaker:DescribeHumanLoop",
        "sagemaker:ListHumanLoops",
        "sagemaker:StopHumanLoop"
      ],
      "Resource": "*"
    }
  ]
}
```

**Don't forget to replace `YOUR-BUCKET-NAME` with your actual bucket!**

### Create the IAM Role

```bash
# Create trust policy for Lambda
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create IAM role
aws iam create-role \
  --role-name ProcessBDAResults-Role \
  --assume-role-policy-document file://trust-policy.json \
  --region us-east-1

# Attach custom policy
aws iam put-role-policy \
  --role-name ProcessBDAResults-Role \
  --policy-name ProcessBDAResults-Policy \
  --policy-document file://processbda-lambda-policy.json \
  --region us-east-1

# Note the Role ARN (you'll need this)
aws iam get-role \
  --role-name ProcessBDAResults-Role \
  --query 'Role.Arn' \
  --output text
```

**Output**: `arn:aws:iam::519677643490:role/ProcessBDAResults-Role`

---

## Step 2: Deploy the ProcessBDAResults Lambda

This Lambda reads BDA results and routes them based on confidence scores.

### Package It Up

```bash
# Create deployment package
cd BDA_Repo
zip -r ProcessBDAResults.zip ProcessBDAResults.py

# OR if you have dependencies (none needed for this Lambda)
# pip install -t package/ boto3
# cd package && zip -r ../ProcessBDAResults.zip . && cd ..
# zip -g ProcessBDAResults.zip ProcessBDAResults.py
```

### Create the Lambda

```bash
aws lambda create-function \
  --function-name ProcessBDAResults \
  --runtime python3.12 \
  --role arn:aws:iam::519677643490:role/ProcessBDAResults-Role \
  --handler ProcessBDAResults.lambda_handler \
  --zip-file fileb://ProcessBDAResults.zip \
  --timeout 60 \
  --memory-size 256 \
  --environment Variables="{
    AWS_REGION=us-east-1,
    DYNAMODB_TABLE=invoices,
    CONFIDENCE_THRESHOLD=0.70,
    A2I_FLOW_ARN=
  }" \
  --region us-east-1
```

Note: We'll add the `A2I_FLOW_ARN` later if you set up human review.

### Verify It Works

```bash
aws lambda get-function \
  --function-name ProcessBDAResults \
  --region us-east-1
```

---

## Step 3: Set Up EventBridge to Catch Completed Jobs

When BDA finishes processing, it sends an event. We need to catch it.

### Create the Rule

```bash
aws events put-rule \
  --name BDA-Invoice-Job-Completion \
  --description "Triggers Lambda when BDA invoice processing job completes successfully" \
  --event-pattern file://eventbridge_rule_bda_completion.json \
  --state ENABLED \
  --region us-east-1
```

### Connect Lambda to the Rule

```bash
# Get Lambda ARN
LAMBDA_ARN=$(aws lambda get-function \
  --function-name ProcessBDAResults \
  --query 'Configuration.FunctionArn' \
  --output text \
  --region us-east-1)

# Add Lambda as target to EventBridge rule
aws events put-targets \
  --rule BDA-Invoice-Job-Completion \
  --targets "Id"="1","Arn"="$LAMBDA_ARN" \
  --region us-east-1
```

### Let EventBridge Invoke Your Lambda

```bash
aws lambda add-permission \
  --function-name ProcessBDAResults \
  --statement-id EventBridgeInvokeProcessBDAResults \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:us-east-1:519677643490:rule/BDA-Invoice-Job-Completion \
  --region us-east-1
```

### Check Everything's Connected

```bash
# Check rule
aws events describe-rule \
  --name BDA-Invoice-Job-Completion \
  --region us-east-1

# Check targets
aws events list-targets-by-rule \
  --rule BDA-Invoice-Job-Completion \
  --region us-east-1
```

---

### Step 4: Test the Pipeline (Without A2I)

---

## Step 4: Test It Out!

Let's upload an invoice and watch the magic happen.

### Upload an Invoice

```bash
# Assuming you have InvoiceJobSubmitter already deployed
aws s3 cp sample-invoice.pdf s3://YOUR-BUCKET/input/
```

### Watch the Logs

**First, InvoiceJobSubmitter kicks off:**
```bash
aws logs tail /aws/lambda/InvoiceJobSubmitter --follow
```

Expected output:
```
Invoking BDA for: s3://YOUR-BUCKET/input/sample-invoice.pdf
BDA job started: arn:aws:bedrock:us-east-1:...:invocation/...
Output location: s3://YOUR-BUCKET/output/sample-invoice_20260104_103000/
```

**Then BDA processes** (~30 seconds)...

**Finally, ProcessBDAResults takes over:**
```bash
aws logs tail /aws/lambda/ProcessBDAResults --follow
```

Expected output (high confidence):
```
Received EventBridge event: {...}
Processing BDA job: 4e360474-cd07-47d3-88b9-b5b8170b54e8
Job status: SUCCESS
Input location: s3://rsm-poc/Screenshot 2025-12-30 130223.jpg
Output location: s3://rsm-poc/output/Screenshot_20260105/job_id/0/
Reading BDA output from: s3://rsm-poc/output/Screenshot_20260105/job_id/0/
S3 Bucket: rsm-poc, Key: output/Screenshot_20260105/job_id/0/custom_output/0/result.json
Successfully read BDA output: 5243 bytes
Extracting invoice data from BDA results...
Extracted invoice: FOP7Y02017-00242218
Vendor: Tech Connect Retail Private Limited
Total: 16599 ₹
Average confidence: 85.23%
Threshold: 70.00%
Storing invoice FOP7Y02017-00242218 in DynamoDB...
Successfully stored invoice FOP7Y02017-00242218 in DynamoDB
```

### Check DynamoDB

Your invoice should be in the database:

```bash
aws dynamodb get-item \
  --table-name invoices \
  --key '{"invoice_id": {"S": "FOP7Y02017-00242218"}}' \
  --region us-east-1
```

Expected output:
```json
{
  "Item": {
    "invoice_id": {"S": "FOP7Y02017-00242218"},
    "vendor_name": {"S": "Flipkart"},
    "total_amount": {"S": "16599"},
    "tax_amount": {"S": "865.35"},
    "average_confidence": {"N": "0.8523"},
    "status": {"S": "high_confidence"},
    "processed_timestamp": {"S": "2026-01-04T10:30:00.123456"},
    ...
  }
}
```

---

## Configuration Quick Reference

### Lambda Environment Variables

**InvoiceJobSubmitter:**

| Variable | What It Does | Example |
|----------|--------------|---------||
| `PROJECT_ARN` | Your BDA project | `arn:aws:bedrock:us-east-1:...:data-automation-project/...` |
| `S3_BUCKET` | Where invoices live | `my-invoice-bucket` |
| `OUTPUT_PREFIX` | Where results go | `output/` |

**ProcessBDAResults:**

| Variable | What It Does | Example | Required? |
|----------|--------------|---------|-----------||
| `AWS_REGION` | AWS region | `us-east-1` | Yes |
| `DYNAMODB_TABLE` | Table name | `invoices` | Yes |
| `CONFIDENCE_THRESHOLD` | When to route to A2I (0-1) | `0.70` | Yes |
| `A2I_FLOW_ARN` | A2I flow for human review | `arn:aws:sagemaker:...` | No |

---

## Making Changes

### Update the Code

```bash
# Make changes to ProcessBDAResults.py

# Re-package
zip -r ProcessBDAResults.zip ProcessBDAResults.py

# Update Lambda
aws lambda update-function-code \
  --function-name ProcessBDAResults \
  --zip-file fileb://ProcessBDAResults.zip \
  --region us-east-1
```

### Change Environment Variables

```bash
aws lambda update-function-configuration \
  --function-name ProcessBDAResults \
  --environment Variables="{
    AWS_REGION=us-east-1,
    DYNAMODB_TABLE=invoices,
    CONFIDENCE_THRESHOLD=0.75,
    A2I_FLOW_ARN=arn:aws:sagemaker:us-east-1:519677643490:flow-definition/invoice-review-flow
  }" \
  --region us-east-1
```

---

---

## Tear It All Down (If You Want)

To remove everything:

```bash
# Delete Lambda function
aws lambda delete-function --function-name ProcessBDAResults --region us-east-1

# Delete EventBridge rule targets
aws events remove-targets \
  --rule BDA-Invoice-Job-Completion \
  --ids "1" \
  --region us-east-1

# Delete EventBridge rule
aws events delete-rule --name BDA-Invoice-Job-Completion --region us-east-1

# Delete IAM role policy
aws iam delete-role-policy \
  --role-name ProcessBDAResults-Role \
  --policy-name ProcessBDAResults-Policy

# Delete IAM role
aws iam delete-role --role-name ProcessBDAResults-Role

# Delete A2I flow definition (if created)
aws sagemaker delete-flow-definition \
  --flow-definition-name invoice-review-flow \
  --region us-east-1
```

---

That's it! You now have a production-ready invoice processing pipeline.

Check CloudWatch Logs if something goes wrong - the Lambdas log everything.
