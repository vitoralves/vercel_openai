import json
import re
import time
import uuid
from typing import Any, Optional

from quota import get_redis

HISTORY_KEY_PREFIX = "ideagen:ideas:"
MAX_IDEAS = 50


def _key(user_id: str) -> str:
    return f"{HISTORY_KEY_PREFIX}{user_id}"


def _parse(raw: Any) -> Optional[dict]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def list_ideas(user_id: str) -> list[dict]:
    redis = get_redis()
    rows = redis.lrange(_key(user_id), 0, MAX_IDEAS - 1) or []
    ideas: list[dict] = []
    for row in rows:
        item = _parse(row)
        if item:
            ideas.append(item)
    return ideas


def save_idea(
    user_id: str,
    *,
    content: str,
    context: str = "",
    scores: Optional[dict] = None,
) -> dict:
    title = _extract_title(content)
    idea = {
        "id": str(uuid.uuid4()),
        "title": title,
        "context": context,
        "content": content,
        "created_at": int(time.time()),
        "favorite": False,
        "scores": scores,
    }
    redis = get_redis()
    key = _key(user_id)
    redis.lpush(key, json.dumps(idea))
    redis.ltrim(key, 0, MAX_IDEAS - 1)
    return idea


def set_favorite(user_id: str, idea_id: str, favorite: bool) -> Optional[dict]:
    redis = get_redis()
    key = _key(user_id)
    rows = redis.lrange(key, 0, MAX_IDEAS - 1) or []
    updated: Optional[dict] = None
    for index, row in enumerate(rows):
        item = _parse(row)
        if not item or item.get("id") != idea_id:
            continue
        item["favorite"] = favorite
        redis.lset(key, index, json.dumps(item))
        updated = item
        break
    return updated


def update_scores(user_id: str, idea_id: str, scores: dict) -> Optional[dict]:
    redis = get_redis()
    key = _key(user_id)
    rows = redis.lrange(key, 0, MAX_IDEAS - 1) or []
    for index, row in enumerate(rows):
        item = _parse(row)
        if not item or item.get("id") != idea_id:
            continue
        item["scores"] = scores
        redis.lset(key, index, json.dumps(item))
        return item
    return None


def _extract_title(content: str) -> str:
    for line in content.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^#+\s*", "", cleaned)
        cleaned = re.sub(r"[*_`]", "", cleaned).strip()
        if cleaned:
            return cleaned[:80]
    return "Untitled idea"
