# Sample BDA Output Files

This folder contains example output files from Amazon Bedrock Data Automation jobs.

## Files

- **standard_output_result.json** - Standard output format with structured markdown representation
- **custom_output_result.json** - Custom output format with field-level confidence scores and explainability data

## Output Structure

BDA generates results in this S3 path structure:
```
s3://bucket/output/filename_timestamp/job_id/0/
  ├── custom_output/0/result.json    # Field extraction with confidence scores
  └── standard_output/0/result.json  # Markdown representation of document
```

## Key Fields in Custom Output

- **matched_blueprint** - Blueprint that matched the document (confidence: 1.0)
- **document_class** - Document type classification
- **inference_result** - Extracted field values
- **explainability_info** - Field-level confidence scores and bounding boxes

Example confidence scores from these samples:
- Invoice number: 88.28%
- Vendor name: 91.41%
- Total amount: 87.50%
- Tax amount: 92.19%

Fields below 70% confidence trigger human review workflows.
