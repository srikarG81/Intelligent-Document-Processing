# Bedrock Knowledge Base Approach - Invoice Processor

## Overview

This approach uses Amazon Bedrock Knowledge Base's **RetrieveAndGenerate** API with Claude 3 Sonnet for chat-with-document invoice extraction.

## Source Repository

The original implementation is available in the AWS Samples repository:
- **Repository:** [genai-invoice-processor](https://github.com/aws-samples/genai-invoice-processor)
- **Local Path:** `C:\personal\Metrics\IDP\3rdApproach\genai-invoice-processor`

## Architecture

```
S3 PDF → Bedrock RetrieveAndGenerate API → Claude 3 Sonnet → Streamlit UI → JSON Export
```

**Key Components:**
- Upload PDF to S3 (or pass inline bytes <5MB)
- Call `retrieve_and_generate` with EXTERNAL_SOURCES
- Three-prompt strategy for extraction, formatting, and summarization
- Streamlit UI for manual review

## How It Works

### 1. Upload Invoice
```python
sources = [{'sourceType': 'S3', 's3Location': {'uri': 's3://bucket/invoice.pdf'}}]
# OR inline bytes (< 6MB request limit)
sources = [{'sourceType': 'BYTE_CONTENT', 'byteContent': {'data': pdf_bytes}}]
```

### 2. Three-Prompt Extraction Strategy
```python
# Prompt 1: Extract all data
"Extract all data in key-value format"

# Prompt 2: Structure as JSON
"Return JSON with: Vendor, InvoiceDate, Total, Currency..."

# Prompt 3: Summarize
"Summarize invoice in 3 lines"
```

### 3. Streamlit Review Interface
- Side-by-side PDF viewer and extracted data
- Navigate between invoices
- Export to JSON

## What Makes It Attractive

✅ **Minimal infrastructure** - Just S3 + Bedrock (no Lambda, Step Functions, SQS)
✅ **Streamlit UI included** - Professional review interface out of the box
✅ **Native PDF understanding** - Claude reads PDFs directly (multi-modal vision)
✅ **Flexible prompting** - Customize extraction fields easily

## Important Limitations

❌ **No field-level confidence scores** - Cannot automatically route to human review
❌ **No bounding boxes** - No visual verification or compliance audit trail
❌ **No deterministic extraction** - LLM output may vary between runs
❌ **Always requires human review** - Not suitable for automated pipelines
❌ **No HITL workflow integration** - Manual review only via Streamlit

## When to Use This Approach

✅ **Best for:**
- Document Q&A and conversational interfaces
- Analyst workflows requiring summaries
- Human-always-in-loop knowledge extraction
- Prototyping and demos with minimal AWS services

❌ **Not suitable for:**
- High-volume automated processing
- Compliance-driven workflows requiring audit trails
- Scenarios needing confidence-based routing
- Production pipelines without human oversight

## Cost Comparison

**Per 1,000 invoices:**
- Bedrock Knowledge Base API: ~$2-3
- No additional compute (can run locally)
- **Total: ~$0.002-0.003 per invoice**

Significantly cheaper than BDA (~$0.015/page) but lacks automation capabilities.

## Setup Instructions

Refer to the original repository for complete setup:

```bash
git clone https://github.com/aws-samples/genai-invoice-processor.git
cd genai-invoice-processor
pip install -r requirements.txt

# Configure S3 bucket in config.yaml
# Run Streamlit app
streamlit run review-invoice-data.py
```

## Key Insight

**Knowledge Bases are production-grade for RAG** (Retrieval-Augmented Generation), not automated IDP. They excel at:
- Document Q&A systems
- Conversational interfaces
- Human-assisted knowledge work

For **structured data extraction** with confidence scoring and automated routing, use BDA or Textract+LLM instead.

## References

- [AWS Bedrock Knowledge Bases Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [RetrieveAndGenerate API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html)
- [Original GitHub Repository](https://github.com/aws-samples/genai-invoice-processor)
