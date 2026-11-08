"""! Тесты низкоуровневого клиента zVirt на моковом транспорте httpx."""
import httpx
import pytest

from backend.app.zvirt.auth import OAuthTokenProvider
from backend.app.zvirt.client import ZvirtClient
from backend.app.zvirt.errors import (
    ZvirtApiError,
    ZvirtAuthError,
    ZvirtTimeoutError,
)

ENGINE = "https://engine.test"
API = ENGINE + "/ovirt-engine/api"
TOKEN_URL = ENGINE + "/ovirt-engine/sso/oauth/token"


class StubTokens(OAuthTokenProvider):
    """! Поставщик токенов без сети: имитирует истечение по invalidate()."""

    def __init__(self):
        self._calls = 0

    def get_token(self) -> str:
        self._calls += 1
        return f"token-{self._calls}"

    def invalidate(self) -> None:
        pass


def make_client(handler) -> ZvirtClient:
    """! Клиент с подменённым транспортом."""
    return ZvirtClient(
        engine_url=ENGINE,
        token_provider=StubTokens(),
        transport=httpx.MockTransport(handler),
    )


def test_get_sends_bearer_and_parses_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ovirt-engine/api/vms"
        assert request.headers["Authorization"] == "Bearer token-1"
        return httpx.Response(200, json={"vm": [{"id": "1", "name": "a"}]})

    client = make_client(handler)
    assert client.get("/vms") == {"vm": [{"id": "1", "name": "a"}]}


def test_401_triggers_single_token_refresh():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.headers["Authorization"])
        if len(attempts) == 1:
            return httpx.Response(401, json={"fault": {"reason": "Unauthorized"}})
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    assert client.get("/vms") == {"ok": True}
    # токен запрошен повторно после инвалидации
    assert attempts == ["Bearer token-1", "Bearer token-2"]


def test_fault_body_becomes_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"fault": {"reason": "Incomplete parameters",
                            "detail": "Vm [name] required for add"}},
        )

    client = make_client(handler)
    with pytest.raises(ZvirtApiError) as err:
        client.post("/vms", body={})
    assert err.value.status_code == 400
    assert err.value.reason == "Incomplete parameters"
    assert err.value.detail == "Vm [name] required for add"


def test_second_401_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"fault": {"reason": "Unauthorized"}})

    client = make_client(handler)
    with pytest.raises(ZvirtApiError) as err:
        client.get("/vms")
    assert err.value.status_code == 401


def test_timeout_maps_to_zvirt_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler)
    with pytest.raises(ZvirtTimeoutError):
        client.get("/vms")


def test_token_provider_requests_oauth_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sso/oauth/token")
        body = request.content.decode()
        assert "grant_type=password" in body
        assert "scope=ovirt-app-api" in body
        assert "admin%40zvirt%40internalsso" in body
        return httpx.Response(200, json={"access_token": "abc", "token_type": "bearer"})

    provider = OAuthTokenProvider(
        ENGINE, "admin@zvirt@internalsso", "pw",
        verify_tls=False, transport=httpx.MockTransport(handler),
    )
    assert provider.get_token() == "abc"
    # повторный вызов отдаёт кешированный токен без нового запроса
    assert provider.get_token() == "abc"


def test_token_provider_rejects_bad_credentials():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    provider = OAuthTokenProvider(
        ENGINE, "u", "bad", verify_tls=False,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ZvirtAuthError):
        provider.get_token()
