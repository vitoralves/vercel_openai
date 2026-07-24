import importlib
import json
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
        self.store: dict[str, object] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value, ex: int | None = None):
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def incr(self, key: str):
        self.store[key] = int(self.store.get(key, 0) or 0) + 1
        return self.store[key]

    def decr(self, key: str):
        self.store[key] = int(self.store.get(key, 0) or 0) - 1
        return self.store[key]

    def expire(self, key: str, seconds: int):
        if key in self.store:
            self.ttls[key] = seconds
            return True
        return False

    def ttl(self, key: str):
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    def lpush(self, key: str, value: str):
        rows = self.store.setdefault(key, [])
        assert isinstance(rows, list)
        rows.insert(0, value)
        return len(rows)

    def ltrim(self, key: str, start: int, stop: int):
        rows = self.store.get(key, [])
        assert isinstance(rows, list)
        self.store[key] = rows[start : stop + 1]
        return True

    def lrange(self, key: str, start: int, stop: int):
        rows = self.store.get(key, [])
        assert isinstance(rows, list)
        if stop < 0:
            return rows[start:]
        return rows[start : stop + 1]

    def eval(self, script: str, keys=None, args=None):
        keys = keys or []
        args = args or []
        key = keys[0]
        if "DECR" in script and "GET" in script:
            current = self.get(key)
            if current is None:
                return 0
            current = int(current)
            if current <= 0:
                return 0
            return self.decr(key)
        if "INCR" in script and "EXPIRE" in script:
            count = int(self.incr(key))
            ttl = self.ttl(key)
            if count == 1 or ttl < 0:
                self.expire(key, int(args[0]))
            return count
        raise NotImplementedError(script[:80])


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
    assert refund_request(user_id) == 0
    assert get_usage(user_id) == 0


def test_refund_never_goes_negative(fake_redis):
    from quota import get_usage, refund_request

    user_id = "user_floor"
    assert refund_request(user_id) == 0
    assert get_usage(user_id) == 0


def test_rate_limit_sets_ttl(fake_redis):
    from ratelimit import GENERATE_LIMIT_PER_HOUR, allow_generate

    user_id = "user_rl"
    ok, remaining = allow_generate(user_id)
    assert ok is True
    assert remaining == GENERATE_LIMIT_PER_HOUR - 1
    assert fake_redis.ttls[f"ideagen:rl:generate:{user_id}"] == 3600

    fake_redis.ttls.pop(f"ideagen:rl:generate:{user_id}", None)
    ok2, _ = allow_generate(user_id)
    assert ok2 is True
    assert fake_redis.ttls[f"ideagen:rl:generate:{user_id}"] == 3600


def test_plans_without_active_status_are_not_premium(fake_redis):
    from billing import _subscription_has_premium

    assert (
        _subscription_has_premium(
            {"status": "canceled", "plans": [{"slug": "premium", "status": "canceled"}]}
        )
        is False
    )
    assert (
        _subscription_has_premium(
            {
                "status": "active",
                "subscription_items": [
                    {"status": "active", "plan": {"slug": "premium_subscription"}}
                ],
            }
        )
        is True
    )


def test_premium_generate_consumes_quota_and_saves(fake_redis):
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
            patch("quota.get_redis", return_value=fake_redis),
            patch("history.get_redis", return_value=fake_redis),
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
            body = response.text
            assert "event: idea" in body
            assert "# Title" in body

        index_module.app.dependency_overrides.clear()


def test_generate_empty_stream_refunds(fake_redis):
    from fastapi.testclient import TestClient
    from quota import get_usage

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
        index_module.app.dependency_overrides[index_module.clerk_guard] = lambda: type(
            "C", (), {"decoded": {"sub": "user_empty"}}
        )()

        with (
            patch("api.index.is_premium_user", return_value=False),
            patch("api.index.allow_generate", return_value=(True, 9)),
            patch("api.index.OpenAI") as openai_cls,
            patch("quota.get_redis", return_value=fake_redis),
        ):
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content=None))]
            openai_cls.return_value.chat.completions.create.return_value = iter(
                [chunk]
            )
            client = TestClient(index_module.app)
            response = client.post("/api/generate", json={})
            assert response.status_code == 200
            _ = response.text
            assert get_usage("user_empty") == 0

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
            patch("quota.get_redis", return_value=fake_redis),
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


def test_score_idea_uses_shared_model():
    from eval import score_idea

    with (
        patch.dict("os.environ", {"OPENAI_MODEL": "gpt-5-nano"}, clear=False),
        patch("eval.OpenAI") as openai_cls,
    ):
        openai_cls.return_value.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content=json.dumps(
                            {
                                "novelty": 8,
                                "feasibility": 7,
                                "overall": 7,
                                "notes": "ok",
                            }
                        )
                    )
                )
            ]
        )
        score_idea("## Problem")
        kwargs = openai_cls.return_value.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-5-nano"
