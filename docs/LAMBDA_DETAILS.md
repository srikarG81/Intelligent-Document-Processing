# Invoice Job Submitter

This Lambda function kicks off the invoice processing workflow. When you upload an invoice to S3, it automatically submits a job to Amazon Bedrock Data Automation (BDA) and returns immediately - no waiting around for results.

## How It Works

1. You upload an invoice to S3
2. Lambda wakes up and submits a BDA job
3. BDA processes the invoice in the background (~30 seconds)
4. EventBridge sends a notification when it's done
5. Another Lambda picks up the results

```
S3 Upload → InvoiceJobSubmitter → BDA Processing → EventBridge → ProcessBDAResults
```

## Why This Works Well

- **No waiting** - Returns immediately after submitting the job (no timeout risk)
- **Event-driven** - EventBridge tells you when jobs complete (no polling)
- **Scalable** - Handle hundreds of invoices without breaking a sweat
- **Organized** - Each job gets its own timestamped output folder

## What You Need

### 1. BDA Project with Blueprint

Create a BDA project and add your invoice blueprint (this tells BDA what fields to extract):

```bash
aws bedrock-data-automation create-data-automation-project \
  --project-name "invoice-processing" \
  --region us-east-1
```

### 2. S3 Bucket

Set up your bucket with an `input/` folder where you'll upload invoices.

### 3. Lambda IAM Role

Your Lambda needs permission to talk to BDA and S3:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeDataAutomationAsync",
        "bedrock:GetDataAutomationStatus"
      ],
      "Resource": [
        "arn:aws:bedrock:*:YOUR_ACCOUNT_ID:data-automation-project/*",
        "arn:aws:bedrock:*:YOUR_ACCOUNT_ID:data-automation-profile/us.data-automation-v1",
        "arn:aws:bedrock:*:YOUR_ACCOUNT_ID:data-automation-invocation/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::your-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

## Configuration

Set these environment variables in your Lambda:

| Variable | What It Does | Example |
|----------|--------------|--------|
| `PROJECT_ARN` | Your BDA project | `arn:aws:bedrock:us-east-1:123456:data-automation-project/abc123` |
| `S3_BUCKET` | Where invoices live | `my-invoice-bucket` |
| `OUTPUT_PREFIX` | Where results go | `output/` |
| `AWS_REGION` | AWS region | `us-east-1` |

## Deployment

### Using AWS Console

1. Create a new Lambda function (Python 3.12, 256MB memory, 3 min timeout)
2. Copy the code from `InvoiceJobSubmitter.py`
3. Add the environment variables above
4. Create an S3 trigger for your bucket:
   - Event: `PUT`
   - Prefix: `input/`
   - Suffix: `.pdf`, `.jpg`, `.png`

Done! Upload an invoice and watch the logs.





## Setting Up EventBridge

To process results when jobs complete, create an EventBridge rule:

```bash
aws events put-rule \
  --name bda-job-completion \
  --event-pattern '{
    "source": ["aws.bedrock"],
    "detail-type": ["Bedrock Data Automation Job State Change"],
    "detail": {"status": ["Success"]}
  }' \
  --state ENABLED
```

Then create a Lambda to process these events (see `ProcessBDAResults.py`).

## Where Results Go

BDA writes results to S3 in this structure:

```
s3://your-bucket/output/
  ├── invoice-001_20260105_143022/
  │   ├── job_id/0/custom_output/0/result.json  # Extracted data with confidence scores
  │   └── job_id/0/standard_output/0/result.json # Standard format
  └── invoice-002_20260105_150145/
      └── ...
```









## The Complete Pipeline

1. **InvoiceJobSubmitter** (this Lambda) - Kicks off BDA jobs
2. **BDA** - Extracts invoice data with confidence scores
3. **EventBridge Rule** - Routes completion events
4. **ProcessBDAResults** - Validates and stores results

## Learn More

- [BDA Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/bda.html)
- [EventBridge Patterns](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns.html)
- [AWS Sample Code](https://github.com/aws-samples/sample-scalable-intelligent-document-processing-with-amazon-bedrock-data-automation)
