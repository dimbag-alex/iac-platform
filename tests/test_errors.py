"""! Модульные тесты иерархии ошибок zVirt и маппинга на HTTP-статусы."""
import pytest

from backend.app.zvirt.errors import (
    ZvirtApiError,
    ZvirtAuthError,
    ZvirtConfigError,
    ZvirtConnectionError,
    ZvirtError,
    ZvirtNotFoundError,
    ZvirtTimeoutError,
    error_detail,
    http_status_for,
)


# --- http_status_for: все классы эквивалентности -------------------------

@pytest.mark.parametrize(
    "error, expected",
    [
        (ZvirtConfigError("нет url"), 503),
        (ZvirtAuthError("отказ"), 502),
        (ZvirtTimeoutError("таймаут"), 504),
        (ZvirtConnectionError("сеть"), 502),
        (ZvirtNotFoundError("ВМ"), 404),
        (ZvirtApiError(409, "Conflict"), 409),
        (ZvirtApiError(400, "Bad request"), 400),
        (ZvirtApiError(500, "Internal"), 500),
        (ZvirtError("прочее"), 500),
    ],
)
def test_http_status_for_mapping(error, expected):
    assert http_status_for(error) == expected


def test_http_status_for_out_of_range_code_becomes_502():
    # нестандартный код гипервизора (вне 4xx/5xx) → 502 Bad Gateway
    assert http_status_for(ZvirtApiError(199, "weird")) == 502
    assert http_status_for(ZvirtApiError(600, "weird")) == 502


def test_not_found_is_404_not_api_passthrough():
    # ZvirtNotFoundError — наследник ZvirtApiError, но статус фиксирован
    assert http_status_for(ZvirtNotFoundError("сеть 'lan'")) == 404


# --- Форматирование и представление --------------------------------------

def test_api_error_message_format():
    err = ZvirtApiError(400, "Incomplete parameters",
                        detail="Vm [name] required", method="POST", path="/vms")
    text = str(err)
    assert "HTTP 400" in text
    assert "POST /vms" in text
    assert "Incomplete parameters" in text
    assert "(Vm [name] required)" in text


def test_not_found_message_contains_object():
    err = ZvirtNotFoundError("логическая сеть 'lan'")
    assert "Not found" in str(err)
    assert err.what == "логическая сеть 'lan'"


def test_error_detail_variants():
    assert error_detail(None) == ""
    assert error_detail(ZvirtAuthError("отказ SSO")) == "отказ SSO"
    err = ZvirtApiError(400, "Bad", detail="detail-text")
    assert error_detail(err) == "Bad: detail-text"
