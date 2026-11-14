"""! GUI-тесты веб-интерфейса платформы (Playwright) и веб-тесты
производительности (CDP Performance domain).

Тесты работают против живого стенда zVirt: фикстура поднимает backend
(uvicorn) на отдельном порту и гоняет сценарии в headless Chromium.
Если стенд недоступен (VPN/лаба выключена), весь модуль пропускается.

Деструктивных действий тесты НЕ выполняют: создание/удаление ВМ и apply
стенда не вызываются — только чтение UI и безопасный предпросмотр.
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "docs" / "testing"
PORT = 8033
BASE = f"http://127.0.0.1:{PORT}"

ZVIRT_ENV = {
    "ZVIRT_URL": os.environ.get("ZVIRT_URL", "https://zhost.lab.loc"),
    "ZVIRT_USERNAME": os.environ.get("ZVIRT_USERNAME", "admin@zvirt@internalsso"),
    "ZVIRT_PASSWORD": os.environ.get("ZVIRT_PASSWORD", "1"),
    "ZVIRT_VERIFY_TLS": "false",
}

playwright = pytest.importorskip("playwright", reason="playwright не установлен")
from playwright.sync_api import sync_playwright  # noqa: E402


def _stand_reachable() -> bool:
    """! Стенд доступен, если отвечает TCP 443 на адресе гипервизора."""
    host = os.environ.get("ZVIRT_HOST_IP", "192.168.31.10")
    try:
        with socket.create_connection((host, 443), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _stand_reachable(),
                                reason="стенд zVirt недоступен")


@pytest.fixture(scope="session")
def server():
    """! Backend платформы как подпроцесс на время GUI-сеанса."""
    env = {**os.environ, **ZVIRT_ENV}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app",
         "--port", str(PORT)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        import httpx
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{BASE}/api/health", timeout=1).status_code == 200:
                    break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError("backend не поднялся за 30 с")
        yield BASE
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    """! Экземпляр Chromium на весь сеанс GUI-тестов."""
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture()
def page(browser, server):
    """! Свежая вкладка браузера на главной странице UI."""
    tab = browser.new_page()
    tab.goto(server, wait_until="networkidle")
    yield tab
    tab.close()


# --- GUI-тесты --------------------------------------------------------------

def test_page_title_and_hypervisor_status(page):
    """! Заголовок страницы и индикатор связи с гипервизором."""
    assert "IaC Platform" in page.title()
    page.wait_for_selector("#hv-dot.ok", timeout=15000)
    assert "zVirt" in page.text_content("#hv-text")


def test_overview_cards_render(page):
    """! Обзорная вкладка: карточки ресурсов и домены хранения."""
    page.wait_for_selector("#overview-cards .card", timeout=15000)
    assert len(page.query_selector_all("#overview-cards .card")) == 4
    page.wait_for_selector("#storage-cards .card", timeout=15000)


def test_tabs_switch(page):
    """! Переключение вкладок навигации меняет видимый раздел."""
    page.click('nav button[data-tab="vms"]')
    assert page.is_visible("#tab-vms.active")
    assert not page.is_visible("#tab-overview")
    page.click('nav button[data-tab="catalog"]')
    assert page.is_visible("#tab-catalog.active")


def test_vm_list_loads(page):
    """! Список ВМ стенда загружается таблицей со статусами."""
    page.click('nav button[data-tab="vms"]')
    page.wait_for_selector("#vms-wrap table tbody tr", timeout=15000)
    rows = page.query_selector_all("#vms-wrap table tbody tr")
    assert len(rows) >= 1
    assert page.query_selector("#vms-wrap .badge") is not None
    page.screenshot(path=str(ARTIFACTS / "ui-vms.png"), full_page=True)


def test_catalog_shows_templates_and_isos(page):
    """! Каталог: шаблоны ВМ и ISO-образы с живого стенда."""
    page.click('nav button[data-tab="catalog"]')
    page.wait_for_selector("#templates .card", timeout=15000)
    names = " ".join(el.text_content() for el in page.query_selector_all("#templates .card"))
    assert "redos" in names.lower() or "Blank" in names
    page.wait_for_selector("#isos .iso", timeout=15000)
    page.screenshot(path=str(ARTIFACTS / "ui-catalog.png"), full_page=True)


def test_create_vm_modal_behavior(page):
    """! Модалка создания ВМ: справочники заполнены, диск скрыт для шаблона ОС."""
    page.click('nav button[data-tab="vms"]')
    page.click("text=+ Создать ВМ")
    assert page.is_visible("#vm-modal.open")
    page.wait_for_selector("#vm-template option", state="attached", timeout=15000)
    options = page.eval_on_selector_all("#vm-template option",
                                        "els => els.map(e => e.value)")
    assert "Blank" in options
    # Для шаблона с ОС поле диска скрывается (диск наследуется от шаблона)
    non_blank = next(o for o in options if o != "Blank")
    page.select_option("#vm-template", non_blank)
    assert not page.is_visible("#vm-disk-row")
    assert page.is_visible("#vm-disk-hint")
    page.select_option("#vm-template", "Blank")
    assert page.is_visible("#vm-disk-row")
    page.click("text=Отмена")
    assert not page.is_visible("#vm-modal.open")


def test_stand_preview_is_read_only(page):
    """! Предпросмотр спецификации стенда (аналог terraform plan)."""
    page.click('nav button[data-tab="stands"]')
    page.fill("#stand-yaml", """stand: guitest
storage_domain: zhost-Local
network: ovirtmgmt
vms:
  - name: guitest-vm1
    memory_mib: 1024
""")
    page.click("text=Предпросмотр")
    page.wait_for_function(
        "document.getElementById('stand-result').textContent.includes('plan')",
        timeout=15000)
    result = json.loads(page.text_content("#stand-result"))
    assert result["plan"][0]["action"] == "create"
    page.screenshot(path=str(ARTIFACTS / "ui-stands.png"), full_page=True)


# --- Веб-тесты производительности --------------------------------------------

def test_performance_page_load(page):
    """! Метрики загрузки страницы: Navigation Timing + CDP Performance."""
    timing = page.evaluate("""() => {
        const t = performance.timing;
        return {
            dns: t.domainLookupEnd - t.domainLookupStart,
            tcp: t.connectEnd - t.connectStart,
            ttfb: t.responseStart - t.requestStart,
            download: t.responseEnd - t.responseStart,
            dom_ready: t.domContentLoadedEventEnd - t.navigationStart,
            full_load: t.loadEventEnd - t.navigationStart,
        };
    }""")
    cdp = page.context.new_cdp_session(page)
    cdp.send("Performance.enable")
    metrics = {m["name"]: m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
    result = {
        "navigation_timing_ms": timing,
        "cdp": {"JSHeapUsedSize_bytes": metrics.get("JSHeapUsedSize"),
                "Documents": metrics.get("Documents"),
                "Nodes": metrics.get("Nodes"),
                "LayoutCount": metrics.get("LayoutCount")},
    }
    assert timing["dom_ready"] < 3000, f"DOM готов слишком долго: {timing['dom_ready']} мс"
    assert timing["ttfb"] < 1000, f"TTFB слишком велик: {timing['ttfb']} мс"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "performance-ui.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2))


def test_performance_api_latency(page, server):
    """! Латентность ключевых API-вызовов из браузера (как у пользователя UI)."""
    endpoints = ["/api/health", "/api/health/hypervisor",
                 "/api/v1/vms", "/api/v1/inventory/storage-domains",
                 "/api/v1/inventory/events?limit=25"]
    latencies = {}
    for ep in endpoints:
        samples = page.evaluate(
            """async (ep) => {
                const out = [];
                for (let i = 0; i < 3; i++) {
                    const t0 = performance.now();
                    await fetch(ep).then(r => r.json());
                    out.push(performance.now() - t0);
                }
                return out;
            }""", ep)
        latencies[ep] = {"min_ms": round(min(samples), 1),
                         "avg_ms": round(sum(samples) / len(samples), 1)}
    path = ARTIFACTS / "performance-api.json"
    path.write_text(json.dumps(latencies, ensure_ascii=False, indent=2))
    # Локальный backend обязан отдавать health мгновенно; инвентарь — < 5 с
    assert latencies["/api/health"]["avg_ms"] < 200
    assert latencies["/api/v1/vms"]["avg_ms"] < 5000
