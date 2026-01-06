import boto3
import json
import traceback
import os
from datetime import datetime
from urllib.parse import unquote_plus

# ===================================================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# ===================================================================

AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
PROJECT_ARN = os.environ.get('PROJECT_ARN')
S3_BUCKET = os.environ.get('S3_BUCKET')
OUTPUT_PREFIX = os.environ.get('OUTPUT_PREFIX', 'output/')

# ===================================================================
# AWS CLIENTS
# ===================================================================

bda_runtime = boto3.client('bedrock-data-automation-runtime', region_name=AWS_REGION)
sts_client = boto3.client('sts')

# Get AWS Account ID
AWS_ACCOUNT_ID = sts_client.get_caller_identity()['Account']

# Managed Profile ARN (AWS-provided, no creation needed)
PROFILE_ARN = f"arn:aws:bedrock:{AWS_REGION}:{AWS_ACCOUNT_ID}:data-automation-profile/us.data-automation-v1"

def lambda_handler(event, context):
    """
    Lambda handler triggered by S3 PUT events
    
    Args:
        event: S3 event containing bucket and object information
        context: Lambda context object
    
    Returns:
        Response dictionary with status and results
    """
    
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Parse S3 event
        s3_event = event['Records'][0]['s3']
        bucket = s3_event['bucket']['name']
        key = unquote_plus(s3_event['object']['key'])
        
        # Construct S3 URI
        input_s3_uri = f"s3://{bucket}/{key}"
        
        # Step 1: Invoke BDA processing
        job_info = invoke_bda_processing(input_s3_uri)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'BDA job submitted successfully',
                'input_file': input_s3_uri,
                'job_arn': job_info['job_arn'],
                'output_s3_uri': job_info['output_s3_uri']
            })
        }
        
    except Exception as e:
        print(f"Error processing invoice: {str(e)}")
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error processing invoice: {str(e)}'
            })
        }
        
def invoke_bda_processing(input_s3_uri):
    """
    Invoke BDA with blueprint
    
    Args:
        input_s3_uri: S3 URI of the invoice to process
    
    Returns:
        Dictionary with job_arn and output_s3_uri
    """
    print(f"Invoking BDA for: {input_s3_uri}")
    
    # Generate output location
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = input_s3_uri.split('/')[-1].split('.')[0]
    output_key = f"{OUTPUT_PREFIX}{file_name}_{timestamp}/"
    output_s3_uri = f"s3://{S3_BUCKET}/{output_key}"
    
    # Invoke BDA with EventBridge notifications enabled
    response = bda_runtime.invoke_data_automation_async(
        dataAutomationProfileArn=PROFILE_ARN,
        inputConfiguration={
            's3Uri': input_s3_uri
        },
        outputConfiguration={
            's3Uri': output_s3_uri
        },
        dataAutomationConfiguration={
            'dataAutomationProjectArn': PROJECT_ARN,
            'stage': 'LIVE'
        },
        notificationConfiguration={
            'eventBridgeConfiguration': {
                'eventBridgeEnabled': True
            }
        }
    )
    
    job_arn = response['invocationArn']
    print(f"BDA job started: {job_arn}")
    print(f"Output location: {output_s3_uri}")
    
    return {
        'job_arn': job_arn,
        'output_s3_uri': output_s3_uri
    }