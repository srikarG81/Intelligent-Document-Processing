# Intelligent Document Processing with Amazon Bedrock Data Automation

This solution demonstrates production-grade invoice processing using Amazon Bedrock Data Automation (BDA) - AWS's fully managed IDP service. It extracts structured data from invoices, provides field-level confidence scores, and automatically routes low-confidence results for human review.

## Why Bedrock Data Automation?

After evaluating AWS-native IDP approaches (BDA, Textract+LLM, Knowledge Base) across production-critical criteria - accuracy, confidence scoring, explainability, HITL integration, and operational complexity - **Bedrock Data Automation stands out for high-volume, compliance-driven workloads** where accuracy, auditability, and automated review are mandatory.

## Repository Structure

```
BDA_Repo/
├── lambda/
│   ├── InvoiceJobSubmitter.py       # Submits BDA jobs on S3 upload
│   └── ProcessBDAResults.py         # Processes results, routes by confidence
├── config/
│   └── eventbridge_rule_bda_completion.json  # EventBridge rule configuration
├── docs/
│   ├── DEPLOYMENT_GUIDE.md          # Step-by-step deployment
│   └── LAMBDA_DETAILS.md            # Lambda function details
├── sample_outputs/
│   ├── standard_output_result.json  # Example BDA standard output
│   └── custom_output_result.json    # Example with confidence scores
├── alternative_approaches/
│   ├── README.md                    # Overview of alternative AWS IDP approaches
│   ├── TEXTRACT_LLM.md             # Textract + Bedrock LLM approach
│   └── BEDROCK_KNOWLEDGE_BASE.md   # Knowledge Base approach
└── README.md                        # This file
```

## How It Works

When you upload an invoice to S3, here's what happens:

1. **S3 Upload** → Triggers InvoiceJobSubmitter Lambda
2. **BDA Processing** → Extracts invoice data asynchronously (~30 seconds)
3. **EventBridge Event** → Notifies when job completes
4. **ProcessBDAResults Lambda** → Calculates confidence scores
5. **Smart Routing**:
   - High confidence (≥70%) → Stored directly in DynamoDB
   - Low confidence (<70%) → Sent to Amazon A2I for human review

## Key Features

- **Field-level confidence scores + bounding boxes** - Know exactly which fields need review (typically 87-94%) with visual grounding
- **Built-in human-in-the-loop (A2I)** - Automatic routing to review queues when confidence falls below threshold
- **Visual grounding and auditability** - Bounding boxes provide compliance-ready audit trails
- **Custom schemas** - Define industry-specific fields with blueprint-based configuration
- **Event-driven architecture** - No polling, efficient EventBridge integration for scalable processing
- **Production-ready** - Multi-page support, document classification, and proper error handling



## Quick Start

1. **Create a BDA Project** in AWS Console with your invoice blueprint

2. **Deploy the Lambda functions** using the [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)

3. **Upload an invoice** to your S3 bucket and watch it process

That's it! Check [Lambda Details](docs/LAMBDA_DETAILS.md) for detailed setup.



## What You Need

- AWS Account with Bedrock access
- S3 bucket for invoices
- DynamoDB table `invoices` with partition key `invoice_id`
- BDA project with your invoice blueprint

## Why Choose BDA for Invoice Processing?

**Managed IDP Service** - BDA is AWS's end-to-end managed intelligent document processing solution using foundation models with custom blueprints.

**Best Suited For:**
- High-volume invoice processing with compliance requirements
- Workflows requiring accuracy, explainability, and automated review
- Organizations needing visual grounding and audit trails
- Teams wanting managed infrastructure over DIY ML pipelines

**Confidence-Based Automation** - Field-level scores enable intelligent routing:

```python
if confidence < 0.70:
    send_to_human_review()  # Automatic escalation
else:
    store_in_database()  # High confidence, auto-approve
```

**Key Differentiators:**
- **vs Textract+LLM**: Built-in HITL workflows, bounding boxes, and confidence thresholds (Textract+LLM requires custom implementation)
- **vs Knowledge Base**: Deterministic extraction with field-level confidence (Knowledge Base excels at document Q&A, not structured extraction)

**Production Quality** - Built-in hallucination mitigation, compliance-ready audit trails, and event-driven scalability.



## Learn More

- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) - Full deployment walkthrough
- [Lambda Details](docs/LAMBDA_DETAILS.md) - Lambda function architecture
- [Sample Outputs](sample_outputs/) - Example BDA results with confidence scores
- [AWS BDA Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/bda.html)
- [AWS Sample Repository](https://github.com/aws-samples/sample-scalable-intelligent-document-processing-with-amazon-bedrock-data-automation)
