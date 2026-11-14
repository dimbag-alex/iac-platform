"""! Модульные тесты сервисного слоя: предикаты и повтор операций (на моках)."""
import httpx
import pytest

from backend.app.zvirt.client import ZvirtClient
from backend.app.zvirt.errors import ZvirtApiError
from backend.app.zvirt.service import ZvirtService, _is_retryable_lock

ENGINE = "https://engine.test"


class StubTokens:
    """! Поставщик токенов без сети (duck-typing вместо OAuthTokenProvider)."""

    def get_token(self) -> str:
        return "t"

    def invalidate(self) -> None:
        pass


def make_service(handler) -> ZvirtService:
    client = ZvirtClient(
        engine_url=ENGINE,
        token_provider=StubTokens(),
        transport=httpx.MockTransport(handler),
    )
    return ZvirtService(client)


# --- _is_retryable_lock ---------------------------------------------------

def test_retryable_lock_only_for_409_with_attempts_left():
    lock = ZvirtApiError(409, "Conflict")
    assert _is_retryable_lock(lock, attempt=0, attempts=6) is True
    assert _is_retryable_lock(lock, attempt=5, attempts=6) is False  # последняя попытка
    other = ZvirtApiError(400, "Bad request")
    assert _is_retryable_lock(other, attempt=0, attempts=6) is False


# --- _is_blank_template -----------------------------------------------------

@pytest.mark.parametrize(
    "name, expected",
    [("Blank", True), ("blank", True), (" BLANK ", True),
     ("redos8.0.3-base", False), ("Blank2", False), ("", False)],
)
def test_is_blank_template(name, expected):
    assert ZvirtService._is_blank_template(name) is expected


# --- vm_action: отклонение неподдерживаемых действий ------------------------

def test_vm_action_rejects_unknown_action():
    service = make_service(lambda request: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="неподдерживаемое действие"):
        service.vm_action("vm-1", "explode")


# --- delete_vm: повтор при заблокированных дисках (HTTP 409) ----------------

def test_delete_vm_retries_on_locked_disks():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(409, json={"fault": {"reason": "disks are locked"}})
        return httpx.Response(200)

    service = make_service(handler)
    service.delete_vm("vm-1", attempts=6, retry_interval=0)
    assert len(calls) == 3  # 2 × 409, затем успех


def test_delete_vm_raises_after_attempts_exhausted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"fault": {"reason": "disks are locked"}})

    service = make_service(handler)
    with pytest.raises(ZvirtApiError) as err:
        service.delete_vm("vm-1", attempts=3, retry_interval=0)
    assert err.value.status_code == 409


def test_delete_vm_does_not_retry_other_errors():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404, json={"fault": {"reason": "not found"}})

    service = make_service(handler)
    with pytest.raises(ZvirtApiError):
        service.delete_vm("vm-1", attempts=6, retry_interval=0)
    assert len(calls) == 1  # 404 не ретраится


# --- get_vm_status: нормализация отсутствующего статуса ---------------------

def test_get_vm_status_unknown_when_missing():
    service = make_service(lambda request: httpx.Response(200, json={}))
    assert service.get_vm_status("vm-1") == "unknown"
