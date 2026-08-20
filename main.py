from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, SecretStr

from backend import AVAILABLE_MODELS, list_available_models, run_loop


app = FastAPI(
    title="Loop Engineering with RAG",
    description="A self-correcting writer, reviewer, and reviser workflow.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class RunLoopRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    model: str | None = Field(default=None, description="Groq model ID.")
    api_key: SecretStr | None = Field(
        default=None,
        description="Optional BYOK Groq key. Falls back to GROQ_API_KEY in .env.",
    )


class RunLoopResponse(BaseModel):
    topic: str
    model: str
    provider: str
    final_answer: str
    final_decision: str
    revision_count: int
    events: list[dict]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "learning-loop-engineering"}


@app.get("/models")
def models(
    x_groq_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, list[str]]:
    """List account models when a BYOK header is supplied, otherwise defaults."""
    if not x_groq_api_key:
        return {"models": AVAILABLE_MODELS}

    try:
        account_models = list_available_models(x_groq_api_key)
        return {"models": account_models or AVAILABLE_MODELS}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not load models from Groq: {exc}",
        ) from exc


@app.post("/run-loop", response_model=RunLoopResponse)
def execute_loop(request: RunLoopRequest) -> dict:
    """Run the writer-reviewer-reviser loop for a topic."""
    api_key = request.api_key.get_secret_value() if request.api_key else None
    try:
        return run_loop(
            topic=request.topic.strip(),
            api_key=api_key,
            model_name=request.model,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The learning loop failed: {exc}",
        ) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
