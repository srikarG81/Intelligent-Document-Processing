import boto3
import json
import traceback
import os
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse

# ===================================================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# ===================================================================

AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'invoices')
CONFIDENCE_THRESHOLD = float(os.environ.get('CONFIDENCE_THRESHOLD', '0.70'))
A2I_FLOW_ARN = os.environ.get('A2I_FLOW_ARN', '')  # Optional - for future A2I integration

# ===================================================================
# AWS CLIENTS
# ===================================================================

s3_client = boto3.client('s3', region_name=AWS_REGION)
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
sagemaker_a2i = boto3.client('sagemaker-a2i-runtime', region_name=AWS_REGION)

# DynamoDB table
table = dynamodb.Table(DYNAMODB_TABLE)

def lambda_handler(event, context):
    """
    Lambda handler triggered by EventBridge when BDA job completes
    
    Event Structure from BDA:
    {
        "version": "0",
        "id": "...",
        "detail-type": "Bedrock Data Automation Job Succeeded",
        "source": "aws.bedrock",
        "account": "...",
        "time": "2026-01-05T14:42:14Z",
        "region": "us-east-1",
        "resources": [],
        "detail": {
            "job_id": "4e360474-cd07-47d3-88b9-b5b8170b54e8",
            "job_status": "SUCCESS",
            "semantic_modality": "Document",
            "input_s3_object": {
                "s3_bucket": "rsm-poc",
                "name": "Screenshot 2025-12-30 130223.jpg"
            },
            "output_s3_location": {
                "s3_bucket": "rsm-poc",
                "name": "output/Screenshot_20260105//job_id/0"
            },
            "job_duration_in_seconds": 16
        }
    }
    
    Args:
        event: EventBridge event from BDA job completion
        context: Lambda context object
    
    Returns:
        Response dictionary with status and results
    """
    
    print(f"Received EventBridge event: {json.dumps(event)}")
    
    try:
        # Extract BDA job details from EventBridge event
        detail = event['detail']
        job_id = detail['job_id']
        job_status = detail['job_status']
        
        # Construct S3 URIs from bucket + name
        input_s3_bucket = detail['input_s3_object']['s3_bucket']
        input_s3_name = detail['input_s3_object']['name']
        input_s3_uri = f"s3://{input_s3_bucket}/{input_s3_name}"
        
        output_s3_bucket = detail['output_s3_location']['s3_bucket']
        output_s3_name = detail['output_s3_location']['name']
        output_s3_uri = f"s3://{output_s3_bucket}/{output_s3_name}/"
        
        print(f"Processing BDA job: {job_id}")
        print(f"Job status: {job_status}")
        print(f"Input location: {input_s3_uri}")
        print(f"Output location: {output_s3_uri}")
        
        # Step 1: Read BDA output from S3
        bda_results = read_bda_output_from_s3(output_s3_uri)
        
        # Step 2: Extract invoice data and calculate confidence
        invoice_data = extract_invoice_data(bda_results, input_s3_uri, output_s3_uri, job_id)
        
        # Step 3: Calculate average confidence
        avg_confidence = invoice_data['average_confidence']
        
        print(f"Average confidence: {avg_confidence:.2%}")
        print(f"Threshold: {CONFIDENCE_THRESHOLD:.2%}")
        
        # Step 4: Route based on confidence
        if avg_confidence >= CONFIDENCE_THRESHOLD:
            # High confidence - Store directly in DynamoDB
            store_in_dynamodb(invoice_data)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Invoice stored in DynamoDB',
                    'invoice_id': invoice_data['invoice_id'],
                    'confidence': avg_confidence,
                    'action': 'stored_in_dynamodb'
                })
            }
        else:
            # Low confidence - Route to A2I for human review
            review_result = send_to_a2i_review(invoice_data, bda_results)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Invoice sent to A2I for human review',
                    'invoice_id': invoice_data['invoice_id'],
                    'confidence': avg_confidence,
                    'action': 'sent_to_a2i',
                    'a2i_result': review_result
                })
            }
        
    except Exception as e:
        print(f"Error processing BDA results: {str(e)}")
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error processing BDA results: {str(e)}'
            })
        }

def read_bda_output_from_s3(output_s3_uri):
    """
    Read BDA output JSON from S3
    
    BDA outputs to: s3://bucket/output/invoice_timestamp/output.json
    
    Args:
        output_s3_uri: S3 URI of the output folder (e.g., s3://bucket/output/invoice_20260104/)
    
    Returns:
        Dictionary with BDA extraction results
    """
    print(f"Reading BDA output from: {output_s3_uri}")
    
    # Parse S3 URI
    parsed = urlparse(output_s3_uri)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip('/')
    
    # BDA outputs to custom_output/0/result.json within the job output folder
    # Pattern: s3://bucket/output/filename_timestamp/job_id/0/custom_output/0/result.json
    if not prefix.endswith('/'):
        prefix = prefix + '/'
    output_key = f"{prefix}custom_output/0/result.json"
    
    # Handle leading slash
    if output_key.startswith('/'):
        output_key = output_key.lstrip('/')
    
    print(f"S3 Bucket: {bucket}, Key: {output_key}")
    
    try:
        response = s3_client.get_object(Bucket=bucket, Key=output_key)
        bda_output = json.loads(response['Body'].read().decode('utf-8'))
        
        print(f"Successfully read BDA output: {len(json.dumps(bda_output))} bytes")
        return bda_output
        
    except s3_client.exceptions.NoSuchKey:
        print(f"ERROR: Output file not found at s3://{bucket}/{output_key}")
        raise Exception(f"BDA output file not found: s3://{bucket}/{output_key}")
    except Exception as e:
        print(f"ERROR reading S3 object: {str(e)}")
        raise

def extract_invoice_data(bda_results, input_s3_uri, output_s3_uri, job_id):
    """
    Extract invoice fields from BDA results
    
    BDA Result Structure (from custom_output/0/result.json):
    {
        "matched_blueprint": {...},
        "document_class": {...},
        "inference_result": {...},
        "explainability_info": [
            {
                "Invoice number": {
                    "success": true,
                    "confidence": 0.8828125,
                    "value": "FOP7Y02017-00242218",
                    "geometry": {...},
                    "type": "string"
                },
                "VendorSupplier name": {...},
                "Total amount due": {...},
                ...
            }
        ]
    }
    
    Args:
        bda_results: Dictionary from BDA output.json
        input_s3_uri: Original input file S3 URI
        output_s3_uri: BDA output folder S3 URI
        job_id: BDA job ID
    
    Returns:
        Dictionary with extracted invoice data and confidence scores
    """
    print("Extracting invoice data from BDA results...")
    
    # BDA result structure: explainability_info[0] contains field-level data
    extraction_data = bda_results.get('explainability_info', [{}])[0]
    
    # Helper function to safely extract field value and confidence
    def get_field(field_name, default_value=None):
        field_data = extraction_data.get(field_name, {})
        return {
            'value': field_data.get('value', default_value),
            'confidence': field_data.get('confidence', 0.0),
            'success': field_data.get('success', False)
        }
    
    # Extract key invoice fields
    invoice_number = get_field('Invoice number')
    vendor_name = get_field('VendorSupplier name')
    total_amount = get_field('Total amount due')
    tax_amount = get_field('Tax amount')
    subtotal = get_field('Subtotal')
    invoice_date = get_field('Invoice date')
    due_date = get_field('Due date')
    currency = get_field('Currency', 'USD')
    
    # Collect all confidence scores for fields that were successfully extracted
    confidence_scores = []
    field_confidences = {}
    
    for field_name, field_data in [
        ('invoice_number', invoice_number),
        ('vendor_name', vendor_name),
        ('total_amount', total_amount),
        ('tax_amount', tax_amount),
        ('subtotal', subtotal),
        ('invoice_date', invoice_date),
        ('due_date', due_date),
        ('currency', currency)
    ]:
        if field_data['success'] and field_data['value'] is not None:
            confidence_scores.append(field_data['confidence'])
            field_confidences[field_name] = field_data['confidence']
    
    # Calculate average confidence
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
    
    # Generate invoice_id (use BDA's invoice number or generate from filename)
    invoice_id = invoice_number['value']
    if not invoice_id:
        # Fallback: use input filename
        filename = input_s3_uri.split('/')[-1].split('.')[0]
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        invoice_id = f"{filename}_{timestamp}"
    
    # Construct invoice data dictionary
    invoice_data = {
        'invoice_id': invoice_id,
        'vendor_name': vendor_name['value'],
        'total_amount': total_amount['value'],
        'tax_amount': tax_amount['value'],
        'subtotal': subtotal['value'],
        'invoice_date': invoice_date['value'],
        'due_date': due_date['value'],
        'currency': currency['value'],
        'average_confidence': avg_confidence,
        'field_confidences': field_confidences,
        'input_s3_uri': input_s3_uri,
        'output_s3_uri': output_s3_uri,
        'job_id': job_id,
        'processed_timestamp': datetime.now().isoformat(),
        'status': 'high_confidence' if avg_confidence >= CONFIDENCE_THRESHOLD else 'needs_review'
    }
    
    print(f"Extracted invoice: {invoice_id}")
    print(f"Vendor: {vendor_name['value']}")
    print(f"Total: {total_amount['value']} {currency['value']}")
    print(f"Average confidence: {avg_confidence:.2%}")
    
    return invoice_data

def store_in_dynamodb(invoice_data):
    """
    Store invoice data in DynamoDB
    
    Args:
        invoice_data: Dictionary with invoice fields
    """
    print(f"Storing invoice {invoice_data['invoice_id']} in DynamoDB...")
    
    # Convert float to Decimal for DynamoDB
    def convert_floats(obj):
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: convert_floats(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_floats(item) for item in obj]
        return obj
    
    # Prepare item for DynamoDB
    item = convert_floats(invoice_data)
    
    try:
        table.put_item(Item=item)
        print(f"Successfully stored invoice {invoice_data['invoice_id']} in DynamoDB")
        
    except Exception as e:
        print(f"ERROR storing in DynamoDB: {str(e)}")
        raise

def send_to_a2i_review(invoice_data, bda_results):
    """
    Send invoice to Amazon Augmented AI (A2I) for human review
    
    This function prepares the invoice for human review when confidence is below threshold.
    
    Args:
        invoice_data: Dictionary with extracted invoice data
        bda_results: Full BDA output for human reviewer context
    
    Returns:
        Dictionary with A2I submission result
    """
    print(f"Preparing invoice {invoice_data['invoice_id']} for A2I human review...")
    print(f"Average confidence: {invoice_data['average_confidence']:.2%} (below threshold: {CONFIDENCE_THRESHOLD:.2%})")
    
    # Check if A2I Flow ARN is configured
    if not A2I_FLOW_ARN:
        print("WARNING: A2I_FLOW_ARN not configured. Storing in DynamoDB with 'needs_review' status.")
        
        # Store in DynamoDB with needs_review status for manual processing
        invoice_data['status'] = 'needs_review'
        invoice_data['review_reason'] = f"Low confidence: {invoice_data['average_confidence']:.2%}"
        store_in_dynamodb(invoice_data)
        
        return {
            'action': 'stored_for_manual_review',
            'message': 'A2I not configured. Stored in DynamoDB with needs_review status.',
            'next_steps': 'Configure A2I_FLOW_ARN environment variable to enable automated human review workflow.'
        }
    
    # A2I is configured - create human loop
    try:
        # Prepare input for human reviewers
        human_loop_input = {
            'invoice_id': invoice_data['invoice_id'],
            'vendor_name': invoice_data['vendor_name'],
            'total_amount': invoice_data['total_amount'],
            'tax_amount': invoice_data['tax_amount'],
            'subtotal': invoice_data['subtotal'],
            'invoice_date': invoice_data['invoice_date'],
            'due_date': invoice_data['due_date'],
            'currency': invoice_data['currency'],
            'average_confidence': invoice_data['average_confidence'],
            'field_confidences': invoice_data['field_confidences'],
            'input_s3_uri': invoice_data['input_s3_uri'],
            'output_s3_uri': invoice_data['output_s3_uri']
        }
        
        # Generate unique human loop name
        human_loop_name = f"invoice-review-{invoice_data['invoice_id']}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Start human loop
        response = sagemaker_a2i.start_human_loop(
            HumanLoopName=human_loop_name,
            FlowDefinitionArn=A2I_FLOW_ARN,
            HumanLoopInput={
                'InputContent': json.dumps(human_loop_input)
            }
        )
        
        print(f"Successfully created A2I human loop: {human_loop_name}")
        print(f"Human loop ARN: {response['HumanLoopArn']}")
        
        # Store in DynamoDB with pending_review status
        invoice_data['status'] = 'pending_review'
        invoice_data['review_reason'] = f"Low confidence: {invoice_data['average_confidence']:.2%}"
        invoice_data['human_loop_name'] = human_loop_name
        invoice_data['human_loop_arn'] = response['HumanLoopArn']
        store_in_dynamodb(invoice_data)
        
        return {
            'action': 'sent_to_a2i',
            'human_loop_name': human_loop_name,
            'human_loop_arn': response['HumanLoopArn']
        }
        
    except Exception as e:
        print(f"ERROR creating A2I human loop: {str(e)}")
        traceback.print_exc()
        
        # Fallback: Store in DynamoDB with error status
        invoice_data['status'] = 'a2i_error'
        invoice_data['review_reason'] = f"A2I error: {str(e)}"
        store_in_dynamodb(invoice_data)
        
        return {
            'action': 'a2i_error',
            'error': str(e),
            'fallback': 'Stored in DynamoDB with a2i_error status'
        }
