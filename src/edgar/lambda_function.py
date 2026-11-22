import json
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

if __package__:
    from .sec_tool.sec_tool import extract_sections, get_latest_ten_k_url, url_to_pdf
else:
    from sec_tool import extract_sections, get_latest_ten_k_url, url_to_pdf

s3_client = boto3.client("s3")
TARGET_BUCKET = os.environ.get("TARGET_BUCKET")


def _extract_params(event: dict) -> dict:
    """
    Supports Bedrock OpenAPI requestBody, Bedrock parameters, and local test dicts.
    """
    # Bedrock OpenAPI POST requestBody
    if "requestBody" in event:
        props = (
            event.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("properties", [])
        )
        return {p["name"]: p["value"] for p in props}

    # Bedrock GET/Function parameters list
    if "parameters" in event:
        return {p["name"]: p["value"] for p in event["parameters"]}

    # 3. Direct local invocation fallback (e.g., {"ticker": "MSFT"})
    return json.loads(event["body"]) if "body" in event else event


def _bedrock_response(event: dict, status_code: int, body_dict: dict) -> dict:
    """
    Formats the response into Bedrock Agent's required Action Group envelope.
    """
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", "SecFilingActionGroup"),
            "apiPath": event.get("apiPath", "/fetch-sec-filing"),
            "httpMethod": event.get("httpMethod", "POST"),
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body_dict)
                }
            },
        },
    }


def lambda_handler(event, context):
    """
    AWS Lambda function for Bedrock Agent Action Group to fetch & store SEC 10-K PDFs.
    """
    try:
        if not TARGET_BUCKET:
            raise ValueError("TARGET_BUCKET environment variable is not set")

        payload = _extract_params(event)
        ticker = payload["ticker"].strip().upper()

        filing_url = get_latest_ten_k_url(ticker)
        sections = extract_sections(filing_url)

        pdf_path = f"/tmp/{ticker}_10K.pdf"
        s3_key = f"filings/{ticker}/{ticker}_10K.pdf"

        # Convert filing to PDF and upload to S3
        url_to_pdf(filing_url, pdf_path)

        s3_client.upload_file(
            pdf_path,
            TARGET_BUCKET,
            s3_key,
            ExtraArgs = {"ContentType": "application/pdf"},
        )

        # Clean up /tmp to prevent disk buildup across warm Lambda invocations
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

        return _bedrock_response(
            event,
            200,
            {
                "ticker": ticker,
                "filing_url": filing_url,
                "pdf": {
                    "bucket": TARGET_BUCKET,
                    "key": s3_key,
                },
                "sections": sections,
            },
        )

    except KeyError as exc:
        return _bedrock_response(
            event, 400, {"error": f"Missing required parameter: {exc.args[0]}"}
        )
    except Exception as exc:
        return _bedrock_response(event, 500, {"error": str(exc)})


if __name__ == "__main__":
    result = lambda_handler({"ticker": "MSFT"}, None)
    print(json.dumps(result, indent=2))
