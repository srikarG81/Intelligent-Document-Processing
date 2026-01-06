# Textract + Bedrock LLM Approach

## Overview

A composable architecture combining Amazon Textract's `analyze_expense` API with Bedrock-hosted LLMs for semantic validation and business logic verification.

## Architecture

```
S3 Upload → Lambda → Textract analyze_expense → Parse Fields → Extract Text → 
Bedrock LLM Validation → DynamoDB + S3 Storage
```

**Key Components:**
1. Textract `analyze_expense` - Pre-trained invoice extraction
2. Text extraction - Get all document text for LLM context
3. Bedrock LLM - Semantic validation and anomaly detection
4. Storage - DynamoDB for structured data, S3 for results

## How It Works

### 1. Textract Extraction
```python
response = textract.analyze_expense(
    Document={'S3Object': {'Bucket': bucket, 'Name': key}}
)

# Extract structured fields with confidence
invoice_number = get_field_value(response, 'INVOICE_NUMBER')
vendor = get_field_value(response, 'VENDOR_NAME')
total = get_field_value(response, 'TOTAL')
tax = get_field_value(response, 'TAX')
```

### 2. Text Extraction for LLM Context
```python
# Get all text lines for semantic analysis
text_lines = [block['Text'] for block in response['Blocks'] 
              if block['BlockType'] == 'LINE']
full_text = '\n'.join(text_lines)
```

### 3. LLM Semantic Validation
```python
prompt = f"""
Analyze this invoice for anomalies:
Vendor: {vendor}
Total: {total}
Tax: {tax}
Subtotal: {subtotal}

Full invoice text:
{full_text}

Check:
1. Does Total = Subtotal + Tax?
2. Is tax percentage reasonable (0-20%)?
3. Any decimal point errors?
4. Any suspicious patterns?
"""

validation = bedrock.invoke_model(model_id='amazon.nova-lite-v1:0', body=prompt)
```

## What Makes It Powerful

✅ **Textract provides structured fields** - Pre-trained for invoices (no blueprint needed)
✅ **Textract includes confidence scores** - Built-in per-field confidence
✅ **LLM validates business logic** - Catches calculation errors, anomalies
✅ **Highly cost-efficient** - ~$0.01 per invoice (vs $0.015 for BDA)
✅ **Low latency** - 5-10 seconds total processing time
✅ **Full architectural control** - Customize routing, rules, workflows

## Real-World Example: Anomaly Detection

**Scenario:** Header shows $3,717.12 but line items total $317.11

```python
# Textract extracts both correctly
header_total = 3717.12  # Confidence: 92%
items_total = 317.11    # Confidence: 95%

# LLM catches the discrepancy
llm_response = "CRITICAL: Decimal point error detected. 
Header total ($3,717.12) is 10x line items total ($317.11)"
```

BDA would extract both values correctly but wouldn't flag the inconsistency.

## Trade-offs

✅ **Advantages over BDA:**
- 60% cheaper (~$8 vs $50 per 1,000 invoices for Textract portion)
- Faster processing (5-10s vs 30s)
- Simpler architecture (single Lambda vs Step Functions)
- More flexible business logic validation

❌ **Disadvantages vs BDA:**
- No built-in HITL workflows (requires custom A2I implementation)
- Limited to Textract's predefined schemas (can't define custom fields easily)
- No bounding boxes for visual verification
- More engineering effort for production deployment

## When to Use This Approach

✅ **Best for:**
- Cost-sensitive pipelines with moderate volumes
- Teams wanting architectural control and flexibility
- Scenarios requiring domain-specific validation (tax rules, vendor verification)
- Standard invoice formats (Textract pre-trained schemas work well)

❌ **Not suitable for:**
- Compliance workflows requiring visual audit trails (bounding boxes)
- Custom field extraction beyond Textract's schemas
- Teams preferring managed HITL workflows
- Multi-page complex documents with custom layouts

## Cost Breakdown

**Per 1,000 invoices:**
- Textract `analyze_expense`: $8
- Bedrock Nova Lite: $0.60
- Lambda: $0.10
- DynamoDB: $0.25
- S3: $0.50
- **Total: ~$9.45 = $0.01 per invoice**

Compare to BDA: ~$60 per 1,000 = $0.06 per invoice

## Implementation Pattern

```python
def lambda_handler(event, context):
    # 1. Get invoice from S3
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # 2. Textract extraction
    textract_response = textract.analyze_expense(...)
    invoice_data = parse_textract_response(textract_response)
    
    # 3. Extract confidence scores
    avg_confidence = calculate_average_confidence(invoice_data)
    
    # 4. LLM semantic validation
    text_lines = extract_text_lines(textract_response)
    validation_result = validate_with_llm(invoice_data, text_lines)
    
    # 5. Route based on confidence + validation
    if avg_confidence >= 0.75 and validation_result['is_valid']:
        store_in_dynamodb(invoice_data)
    else:
        # Custom HITL workflow
        send_to_review_queue(invoice_data, validation_result)
```

## HITL Implementation Note

Unlike BDA's built-in A2I integration, this approach requires custom implementation:

```python
# Option 1: Simple review queue
sqs.send_message(
    QueueUrl=REVIEW_QUEUE_URL,
    MessageBody=json.dumps({
        'invoice_id': invoice_id,
        'confidence': avg_confidence,
        'validation_issues': validation_result['issues'],
        's3_uri': f's3://{bucket}/{key}'
    })
)

# Option 2: Integrate with A2I manually
a2i_client.start_human_loop(
    HumanLoopName=f'invoice-review-{invoice_id}',
    FlowDefinitionArn=A2I_FLOW_ARN,
    HumanLoopInput={'InputContent': json.dumps(invoice_data)}
)
```

## Key Insight

**Textract + LLM is production-capable** for teams that:
- Want cost optimization and low latency
- Need semantic validation capabilities
- Have engineering resources for custom HITL workflows
- Don't require visual grounding for compliance

For **managed HITL, bounding boxes, and custom blueprints**, use BDA instead.

## References

- [Amazon Textract analyze_expense API](https://docs.aws.amazon.com/textract/latest/dg/API_AnalyzeExpense.html)
- [Amazon Bedrock Inference](https://docs.aws.amazon.com/bedrock/latest/userguide/inference.html)
- [Detailed Comparison](../../IDP_APPROACHES_ANALYSIS.md)
