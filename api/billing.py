import logging
import os
from typing import Any

import httpx

PREMIUM_PLAN_SLUGS = {
    "premium_subscription",
    "premium",
}
PREMIUM_NAME_HINTS = ("premium",)
CLERK_API_BASE = "https://api.clerk.com/v1"

logger = logging.getLogger("ideagen.billing")


def is_premium_user(user_id: str) -> bool:
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
        return False

    if response.status_code == 404:
        return False
    if response.status_code >= 400:
        logger.warning(
            "billing_subscription_http_error user=%s status=%s body=%s",
            user_id[:8],
            response.status_code,
            response.text[:200],
        )
        return False

    try:
        data: dict[str, Any] = response.json()
    except ValueError:
        logger.warning("billing_subscription_invalid_json user=%s", user_id[:8])
        return False

    premium = _subscription_has_premium(data)
    logger.info("billing_check user=%s premium=%s", user_id[:8], premium)
    return premium


def _subscription_has_premium(data: dict[str, Any]) -> bool:
    status = (data.get("status") or "").lower()
    if status not in {"active", "trialing", "past_due", ""}:
        # Still inspect items; top-level status can differ from item status.
        pass

    if _plan_is_premium(data.get("plan") or {}) and status in {
        "active",
        "trialing",
        "past_due",
    }:
        return True

    items = data.get("subscription_items") or data.get("items") or []
    for item in items:
        item_status = (item.get("status") or "").lower()
        if item_status not in {"active", "trialing", "past_due"}:
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
