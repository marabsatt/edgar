import json
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

if __package__:
    from .sec_tool import extract_sections, get_latest_ten_k_url, url_to_pdf
else:
    from sec_tool import extract_sections, get_latest_ten_k_url, url_to_pdf

s3_client = boto3.client('s3')
TARGET_BUCKET = os.environ.get('TARGET_BUCKET')


def lambda_handler(event, context):
    '''
    AWS Lambda function to put raw PDFs into S3
    '''
    try:
        if not TARGET_BUCKET:
            raise ValueError("TARGET_BUCKET environment variable is not set")

        payload = json.loads(event["body"]) if "body" in event else event
        ticker = payload["ticker"].strip().upper()

        filing_url = get_latest_ten_k_url(ticker)
        sections = extract_sections(filing_url)

        pdf_path = f"/tmp/{ticker}_10K.pdf"
        s3_key = f"filings/{ticker}/{ticker}_10K.pdf"

        url_to_pdf(filing_url, pdf_path)

        s3_client.upload_file(
            pdf_path,
            TARGET_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": "application/pdf"},
        )

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ticker": ticker,
                "filing_url": filing_url,
                "pdf": {
                    "bucket": TARGET_BUCKET,
                    "key": s3_key,
                },
                "sections": sections,
            }),
        }

    except KeyError as exc:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": f"Missing required parameter: {exc.args[0]}"
            }),
        }


if __name__ == "__main__":
    result = lambda_handler({"ticker": "MSFT"}, None)
    print(json.dumps(result, indent=2))
