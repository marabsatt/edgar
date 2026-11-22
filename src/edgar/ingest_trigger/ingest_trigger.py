import os
import urllib.parse
import boto3
from botocore.exceptions import ClientError

bedrock_agent = boto3.client("bedrock-agent")
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID")
DATA_SOURCE_ID = os.environ.get("DATA_SOURCE_ID")


def lambda_handler(event, context):
    """AWS Lambda function triggered by S3 ObjectCreated events to sync Bedrock KB."""
    if not KNOWLEDGE_BASE_ID or not DATA_SOURCE_ID:
        raise ValueError("KNOWLEDGE_BASE_ID and DATA_SOURCE_ID environment variables must be set")

    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "No records to process"}

    for record in records:
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        print(f"Detected {record['eventName']} for s3://{bucket_name}/{object_key}")

    try:
        response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            dataSourceId=DATA_SOURCE_ID,
            description=f"Triggered by S3 upload ({len(records)} object(s))",
        )
        job = response["ingestionJob"]
        print(f"Started ingestion job: {job['ingestionJobId']} | Status: {job['status']}")

        return {
            "statusCode": 200,
            "ingestionJobId": job["ingestionJobId"],
            "status": job["status"],
        }

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ConflictException":
            # An ingestion job is already running for this data source
            print("Ingestion job already in progress; skipping duplicate trigger.")
            return {"statusCode": 202, "body": "Ingestion job already in progress"}
        raise
