import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
sys.path.insert(0, str(API))
sys.path.insert(0, str(ROOT))


class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}

    def get(self, key: str):
        return self.store.get(key)

    def incr(self, key: str):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def decr(self, key: str):
        self.store[key] = int(self.store.get(key, 0)) - 1
        return self.store[key]

    def expire(self, key: str, seconds: int):
        return True


@pytest.fixture()
def fake_redis():
    redis = FakeRedis()
    with patch("quota.get_redis", return_value=redis):
        yield redis


def test_free_user_blocked_after_one_request(fake_redis):
    from quota import FREE_LIFETIME_LIMIT, get_usage, reserve_request

    user_id = "user_free_1"
    assert FREE_LIFETIME_LIMIT == 1

    ok1, used1 = reserve_request(user_id, FREE_LIFETIME_LIMIT)
    ok2, used2 = reserve_request(user_id, FREE_LIFETIME_LIMIT)

    assert ok1 is True and used1 == 1
    assert ok2 is False and used2 == 1
    assert get_usage(user_id) == 1


def test_premium_user_blocked_after_five_requests(fake_redis):
    from quota import PREMIUM_LIFETIME_LIMIT, get_usage, reserve_request

    user_id = "user_premium_1"
    assert PREMIUM_LIFETIME_LIMIT == 5

    results = [reserve_request(user_id, PREMIUM_LIFETIME_LIMIT) for _ in range(6)]
    assert all(ok for ok, _ in results[:5])
    assert results[5] == (False, 5)
    assert get_usage(user_id) == 5


def test_refund_on_empty_reservation(fake_redis):
    from quota import FREE_LIFETIME_LIMIT, get_usage, refund_request, reserve_request

    user_id = "user_refund"
    ok, used = reserve_request(user_id, FREE_LIFETIME_LIMIT)
    assert ok and used == 1
    refund_request(user_id)
    assert get_usage(user_id) == 0


def test_premium_generate_consumes_quota(fake_redis):
    from fastapi.testclient import TestClient

    env = {
        "CLERK_JWKS_URL": "https://example.clerk.accounts.dev/.well-known/jwks.json",
        "CLERK_SECRET_KEY": "sk_test",
        "UPSTASH_REDIS_REST_URL": "https://example.upstash.io",
        "UPSTASH_REDIS_REST_TOKEN": "token",
        "OPENAI_API_KEY": "sk-test",
    }

    with patch.dict("os.environ", env, clear=False):
        import api.index as index_module

        importlib.reload(index_module)

        class FakeCreds:
            decoded = {"sub": "user_premium_1"}

        def override_auth():
            return FakeCreds()

        index_module.app.dependency_overrides[index_module.clerk_guard] = override_auth

        with (
            patch("api.index.is_premium_user", return_value=True),
            patch("api.index.allow_generate", return_value=(True, 9)),
            patch("api.index.OpenAI") as openai_cls,
        ):
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content="# Title\n"))]
            openai_cls.return_value.chat.completions.create.return_value = iter(
                [chunk]
            )

            client = TestClient(index_module.app)
            response = client.post(
                "/api/generate",
                json={"context": "DevTools"},
            )

            assert response.status_code == 200
            assert response.headers.get("X-Plan") == "premium"
            assert response.headers.get("X-Limit") == "5"
            assert response.headers.get("X-Used") == "1"
            assert response.headers.get("X-Remaining") == "4"
            _ = response.text

        index_module.app.dependency_overrides.clear()


def test_score_consumes_same_quota(fake_redis):
    from fastapi.testclient import TestClient

    env = {
        "CLERK_JWKS_URL": "https://example.clerk.accounts.dev/.well-known/jwks.json",
        "CLERK_SECRET_KEY": "sk_test",
        "UPSTASH_REDIS_REST_URL": "https://example.upstash.io",
        "UPSTASH_REDIS_REST_TOKEN": "token",
        "OPENAI_API_KEY": "sk-test",
    }

    with patch.dict("os.environ", env, clear=False):
        import api.index as index_module

        importlib.reload(index_module)

        class FakeCreds:
            decoded = {"sub": "user_free_score"}

        index_module.app.dependency_overrides[index_module.clerk_guard] = (
            lambda: FakeCreds()
        )

        with (
            patch("api.index.is_premium_user", return_value=False),
            patch("api.index.allow_score", return_value=(True, 19)),
            patch(
                "api.index.score_idea",
                return_value={
                    "novelty": 7,
                    "feasibility": 8,
                    "overall": 7,
                    "notes": "ok",
                },
            ),
        ):
            client = TestClient(index_module.app)
            first = client.post(
                "/api/ideas/score",
                json={"content": "## Problem\nTest"},
            )
            second = client.post(
                "/api/ideas/score",
                json={"content": "## Problem\nTest again"},
            )

            assert first.status_code == 200
            assert first.json()["usage"]["used"] == 1
            assert first.json()["usage"]["remaining"] == 0
            assert second.status_code == 402

        index_module.app.dependency_overrides.clear()
