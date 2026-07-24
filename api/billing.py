import logging
import os
from typing import Any, Optional

import httpx

from quota import get_redis

PREMIUM_PLAN_SLUGS = {
    "premium_subscription",
    "premium",
}
PREMIUM_NAME_HINTS = ("premium",)
ACTIVE_STATUSES = {"active", "trialing", "past_due"}
CLERK_API_BASE = "https://api.clerk.com/v1"
PREMIUM_CACHE_PREFIX = "ideagen:premium:"
PREMIUM_CACHE_TTL_SECONDS = 60
PREMIUM_STALE_TTL_SECONDS = 86400

logger = logging.getLogger("ideagen.billing")


def is_premium_user(user_id: str) -> bool:
    cached = _get_cached_premium(user_id)
    if cached is not None:
        return cached

    secret = os.getenv("CLERK_SECRET_KEY")
    if not secret:
        logger.warning("CLERK_SECRET_KEY missing; treating user as free")
        return False

    try:
        response = httpx.get(
            f"{CLERK_API_BASE}/users/{user_id}/billing/subscription",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
    except httpx.HTTPError:
        logger.exception("billing_subscription_request_failed user=%s", user_id[:8])
        return _fallback_premium(user_id)

    if response.status_code == 404:
        _set_cached_premium(user_id, False)
        return False
    if response.status_code >= 400:
        logger.warning(
            "billing_subscription_http_error user=%s status=%s body=%s",
            user_id[:8],
            response.status_code,
            response.text[:200],
        )
        return _fallback_premium(user_id)

    try:
        data: dict[str, Any] = response.json()
    except ValueError:
        logger.warning("billing_subscription_invalid_json user=%s", user_id[:8])
        return _fallback_premium(user_id)

    premium = _subscription_has_premium(data)
    _set_cached_premium(user_id, premium)
    logger.info("billing_check user=%s premium=%s", user_id[:8], premium)
    return premium


def _cache_key(user_id: str) -> str:
    return f"{PREMIUM_CACHE_PREFIX}{user_id}"


def _stale_key(user_id: str) -> str:
    return f"{PREMIUM_CACHE_PREFIX}stale:{user_id}"


def _get_cached_premium(user_id: str) -> Optional[bool]:
    try:
        value = get_redis().get(_cache_key(user_id))
    except Exception:
        logger.exception("premium_cache_read_failed user=%s", user_id[:8])
        return None
    if value is None:
        return None
    return str(value) in {"1", "true", "True"}


def _set_cached_premium(user_id: str, premium: bool) -> None:
    try:
        redis = get_redis()
        flag = "1" if premium else "0"
        redis.set(_cache_key(user_id), flag, ex=PREMIUM_CACHE_TTL_SECONDS)
        redis.set(_stale_key(user_id), flag, ex=PREMIUM_STALE_TTL_SECONDS)
    except Exception:
        logger.exception("premium_cache_write_failed user=%s", user_id[:8])


def _fallback_premium(user_id: str) -> bool:
    try:
        value = get_redis().get(_stale_key(user_id))
        if value is not None:
            premium = str(value) in {"1", "true", "True"}
            logger.warning(
                "billing_fallback_stale user=%s premium=%s",
                user_id[:8],
                premium,
            )
            return premium
    except Exception:
        logger.exception("premium_stale_read_failed user=%s", user_id[:8])
    return False


def _subscription_has_premium(data: dict[str, Any]) -> bool:
    status = (data.get("status") or "").lower()

    if _plan_is_premium(data.get("plan") or {}) and status in ACTIVE_STATUSES:
        return True

    items = data.get("subscription_items") or data.get("items") or []
    for item in items:
        item_status = (item.get("status") or "").lower()
        if item_status not in ACTIVE_STATUSES:
            continue
        plan = item.get("plan") or {}
        if _plan_is_premium(plan):
            return True
        if _plan_is_premium(
            {
                "slug": item.get("slug"),
                "name": item.get("name"),
                "id": item.get("plan_id") or item.get("id"),
            }
        ):
            return True

    for plan in data.get("plans") or []:
        plan_status = (plan.get("status") or "").lower()
        if plan_status not in ACTIVE_STATUSES:
            continue
        if _plan_is_premium(plan):
            return True

    return False


def _plan_is_premium(plan: dict[str, Any]) -> bool:
    slug = str(plan.get("slug") or "").strip().lower()
    name = str(plan.get("name") or "").strip().lower()
    plan_id = str(plan.get("id") or "").strip().lower()

    if slug in PREMIUM_PLAN_SLUGS:
        return True
    if any(slug == hint or slug.endswith(f"_{hint}") for hint in PREMIUM_NAME_HINTS):
        return True
    if name in PREMIUM_PLAN_SLUGS or name in PREMIUM_NAME_HINTS:
        return True
    if "premium_subscription" in plan_id:
        return True
    return False
