import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
from openai import OpenAI
from pydantic import BaseModel, Field

_API_DIR = Path(__file__).resolve().parent
_ROOT = _API_DIR.parent
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

load_dotenv(_ROOT / ".env.local", override=True)
load_dotenv(_ROOT / ".env", override=False)

from billing import is_premium_user  # noqa: E402
from eval import score_idea  # noqa: E402
from history import list_ideas, save_idea, set_favorite, update_scores  # noqa: E402
from quota import (  # noqa: E402
    get_usage,
    limit_for_plan,
    refund_request,
    reserve_request,
)
from ratelimit import allow_generate, allow_score  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ideagen")

app = FastAPI(
    title="IdeaGen API",
    description="Authenticated business-idea generation with lifetime request quotas.",
    version="1.2.0",
)

_jwks_url = (os.getenv("CLERK_JWKS_URL") or "").strip()
if not _jwks_url.startswith(("http://", "https://")):
    raise RuntimeError(
        "CLERK_JWKS_URL is missing or invalid. "
        "Set it to https://<your-clerk-frontend-api>/.well-known/jwks.json"
    )

clerk_config = ClerkConfig(jwks_url=_jwks_url)
clerk_guard = ClerkHTTPBearer(clerk_config)

MAX_CONTEXT_CHARS = 500
DEFAULT_FREE_MODEL = "gpt-5-nano"
DEFAULT_PREMIUM_MODEL = "gpt-5-nano"


class GenerateRequest(BaseModel):
    context: Optional[str] = Field(default=None, max_length=MAX_CONTEXT_CHARS)


class SaveIdeaRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    context: Optional[str] = Field(default="", max_length=MAX_CONTEXT_CHARS)


class FavoriteRequest(BaseModel):
    favorite: bool = True


class ScoreRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    idea_id: Optional[str] = None


def _sanitize_context(value: Optional[str]) -> str:
    text = (value or "").strip()
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text[:MAX_CONTEXT_CHARS]


def _model_for_plan(premium: bool) -> str:
    if premium:
        return os.getenv("OPENAI_MODEL_PREMIUM", DEFAULT_PREMIUM_MODEL)
    return os.getenv("OPENAI_MODEL_FREE", DEFAULT_FREE_MODEL)


def _usage_payload(user_id: str, premium: bool, used: Optional[int] = None) -> dict:
    limit = limit_for_plan(premium)
    current = get_usage(user_id) if used is None else used
    return {
        "plan": "premium" if premium else "free",
        "used": current,
        "limit": limit,
        "remaining": max(limit - current, 0),
    }


def _quota_exceeded_detail(user_id: str, premium: bool) -> dict:
    usage = _usage_payload(user_id, premium)
    if premium:
        message = (
            "Premium request limit reached. Generate and score share the same credits."
        )
    else:
        message = (
            "Free tier limit reached. Upgrade to Premium for more requests "
            "(generate and score share the same credits)."
        )
    return {
        "error": "quota_exceeded",
        "message": message,
        **usage,
    }


def _structured_prompt(context: str) -> str:
    base = (
        "Create a new business idea for the AI agent economy.\n"
        "Respond in Markdown with EXACTLY these top-level sections, in order:\n"
        "## Problem\n"
        "## ICP\n"
        "## MVP\n"
        "## Moat\n"
        "## Risks\n"
        "## Go-to-market\n"
        "Use concise bullet points under each section. Start with a short H1 title."
    )
    if context:
        return f"{base}\n\nUser context to incorporate:\n{context}"
    return base


@app.get("/api/usage")
def usage(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded["sub"]
    premium = is_premium_user(user_id)
    return _usage_payload(user_id, premium)


@app.get("/api/ideas")
def get_ideas(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded["sub"]
    return {"ideas": list_ideas(user_id)}


@app.post("/api/ideas")
def create_idea(
    body: SaveIdeaRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]
    idea = save_idea(
        user_id,
        content=body.content.strip(),
        context=_sanitize_context(body.context),
    )
    return idea


@app.post("/api/ideas/{idea_id}/favorite")
def favorite_idea(
    idea_id: str,
    body: FavoriteRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]
    updated = set_favorite(user_id, idea_id, body.favorite)
    if not updated:
        raise HTTPException(status_code=404, detail="Idea not found")
    return updated


@app.post("/api/ideas/score")
def score_endpoint(
    body: ScoreRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]
    premium = is_premium_user(user_id)
    limit = limit_for_plan(premium)

    allowed_rl, rl_remaining = allow_score(user_id)
    if not allowed_rl:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "message": "Too many score requests. Try again in about an hour.",
                "remaining": rl_remaining,
            },
        )

    allowed, used_after = reserve_request(user_id, limit)
    if not allowed:
        raise HTTPException(
            status_code=402,
            detail=_quota_exceeded_detail(user_id, premium),
        )

    started = time.perf_counter()
    try:
        scores = score_idea(body.content.strip())
    except Exception:
        refund_request(user_id)
        logger.exception("score_failed user=%s", user_id[:8])
        raise HTTPException(status_code=502, detail="Failed to score idea")

    if body.idea_id:
        update_scores(user_id, body.idea_id, scores)

    logger.info(
        "score_ok user=%s premium=%s used=%d latency_ms=%d",
        user_id[:8],
        premium,
        used_after,
        int((time.perf_counter() - started) * 1000),
    )
    return {
        "scores": scores,
        "usage": _usage_payload(user_id, premium, used=used_after),
    }


@app.post("/api/generate")
def generate(
    body: GenerateRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]
    premium = is_premium_user(user_id)
    reserved = False
    used_after = 0
    started = time.perf_counter()

    allowed_rl, rl_remaining = allow_generate(user_id)
    if not allowed_rl:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "message": "Too many generate requests. Try again in about an hour.",
                "remaining": rl_remaining,
            },
        )

    limit = limit_for_plan(premium)
    allowed, used_after = reserve_request(user_id, limit)
    if not allowed:
        raise HTTPException(
            status_code=402,
            detail=_quota_exceeded_detail(user_id, premium),
        )
    reserved = True

    context = _sanitize_context(body.context)
    prompt_content = _structured_prompt(context)
    model = _model_for_plan(premium)

    client = OpenAI()
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt_content}],
            stream=True,
        )
    except Exception:
        refund_request(user_id)
        logger.exception("generate_start_failed user=%s model=%s", user_id[:8], model)
        raise HTTPException(status_code=502, detail="Failed to start generation")

    usage_info = _usage_payload(user_id, premium, used=used_after)

    def event_stream():
        produced = False
        try:
            for chunk in stream:
                text = chunk.choices[0].delta.content
                if not text:
                    continue
                produced = True
                lines = text.split("\n")
                for line in lines[:-1]:
                    yield f"data: {line}\n\n"
                    yield "data:  \n"
                yield f"data: {lines[-1]}\n\n"
        except Exception:
            if reserved:
                refund_request(user_id)
            logger.exception("generate_stream_failed user=%s", user_id[:8])
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)
        if reserved and not produced:
            refund_request(user_id)
            logger.info(
                "generate_empty user=%s premium=%s latency_ms=%d",
                user_id[:8],
                premium,
                latency_ms,
            )
        else:
            logger.info(
                "generate_ok user=%s premium=%s produced=%s used=%d latency_ms=%d model=%s",
                user_id[:8],
                premium,
                produced,
                used_after,
                latency_ms,
                model,
            )

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Plan": usage_info["plan"],
        "X-Used": str(usage_info["used"]),
        "X-Limit": str(usage_info["limit"]),
        "X-Remaining": str(usage_info["remaining"]),
        "X-Model": model,
    }

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=headers,
    )


@app.get("/api")
def legacy_root(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    return JSONResponse(
        status_code=405,
        content={
            "error": "use_post_generate",
            "message": "Use POST /api/generate with an Authorization bearer token.",
        },
    )
