import logging
import os
import re
import uuid
from collections.abc import Iterator, Mapping
from functools import lru_cache
from typing import Annotated, Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator


LOGGER = logging.getLogger(__name__)
SESSION_ID_PATTERN = re.compile(r"^[0-9A-Za-z._:-]{2,100}$")

app = FastAPI(title="EDGAR Bedrock Agent Orchestrator")


class PromptRequest(BaseModel):
    """
    Request sent by the client through CloudFront.
    """

    model_config = ConfigDict(populate_by_name=True)

    prompt: str = Field(min_length=1, max_length=25_000_000)
    session_id: str | None = Field(
        default=None,
        alias="sessionId",
        min_length=2,
        max_length=100,
        pattern=SESSION_ID_PATTERN.pattern,
    )
    end_session: bool = Field(default=False, alias="endSession")

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt cannot be blank")
        return value


@lru_cache(maxsize=1)
def get_bedrock_client():
    """
    Reuse the Bedrock Agent Runtime client across warm invocations.
    """
    return boto3.client("bedrock-agent-runtime")


def get_agent_configuration() -> tuple[str, str]:
    agent_id = os.environ.get("BEDROCK_AGENT_ID")
    agent_alias_id = os.environ.get("BEDROCK_AGENT_ALIAS_ID")

    if not agent_id or not agent_alias_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS_ID must be configured"
            ),
        )

    return agent_id, agent_alias_id


def resolve_session_id(body_session_id: str | None, header_session_id: str | None) -> str:
    """
    Use the body/header session ID or securely generate a new one.
    """
    session_id = body_session_id or header_session_id or str(uuid.uuid4())

    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "sessionId must be 2-100 characters and contain only letters, "
                "numbers, periods, underscores, colons, or hyphens"
            ),
        )

    return session_id


def iter_completion_chunks(completion: Iterator[Mapping[str, Any]]) -> Iterator[bytes]:
    """
    Yield only text chunks from the Bedrock Agent event stream.
    """
    try:
        for event in completion:
            chunk = event.get("chunk")
            if chunk and chunk.get("bytes"):
                yield chunk["bytes"]
    except (BotoCoreError, ClientError):
        LOGGER.exception("Bedrock event stream failed")
        raise
    finally:
        close = getattr(completion, "close", None)
        if callable(close):
            close()


@app.get("/")
def health_check() -> dict[str, str]:
    """
    Lambda Web Adapter readiness endpoint.
    """
    return {"status": "healthy"}


@app.post("/invoke", response_class=StreamingResponse)
def invoke_agent(
    request: PromptRequest,
    x_session_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """
    Invoke the configured Bedrock Agent and stream its response to the client."""
    agent_id, agent_alias_id = get_agent_configuration()
    session_id = resolve_session_id(request.session_id, x_session_id)

    try:
        response = get_bedrock_client().invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=session_id,
            inputText=request.prompt,
            endSession=request.end_session,
            streamingConfigurations={"streamFinalResponse": True},
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("Unable to invoke Bedrock Agent")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to invoke Bedrock Agent",
        ) from exc

    completion = response.get("completion")
    if completion is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Bedrock Agent returned no completion stream",
        )

    return StreamingResponse(
        iter_completion_chunks(completion),
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Session-Id": session_id,
            "Access-Control-Expose-Headers": "X-Session-Id",
            "Cache-Control": "no-cache, no-transform",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
