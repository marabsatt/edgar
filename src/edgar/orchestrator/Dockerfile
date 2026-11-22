FROM public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 AS lambda-adapter
FROM public.ecr.aws/docker/library/python:3.13-slim

COPY --from=lambda-adapter /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app

RUN pip install --no-cache-dir \
    "boto3>=1.44.8" \
    "fastapi>=0.122.0" \
    "uvicorn>=0.38.0"

COPY src /app/src

ENV AWS_LWA_INVOKE_MODE=response_stream \
    PORT=8080 \
    PYTHONPATH=/app/src

EXPOSE 8080

CMD ["uvicorn", "edgar.orchestrator.orchestrator:app", "--host", "0.0.0.0", "--port", "8080"]
