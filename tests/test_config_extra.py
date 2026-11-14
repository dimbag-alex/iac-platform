"""! Модульные тесты разбора конфигурации: .env, числовые и булевы переменные."""
import pytest

from backend.app.config import _env_bool, _env_float, _load_dotenv, _parse_env_line


# --- _parse_env_line: эквивалентные классы входных строк -----------------

def test_parse_env_line_plain_pair():
    assert _parse_env_line("ZVIRT_URL=https://host") == ("ZVIRT_URL", "https://host")


def test_parse_env_line_strips_quotes_and_spaces():
    assert _parse_env_line(' KEY = "value" ') == ("KEY", "value")
    assert _parse_env_line("KEY='quoted'") == ("KEY", "quoted")


def test_parse_env_line_value_may_contain_equals():
    assert _parse_env_line("PASSWORD=a=b=c") == ("PASSWORD", "a=b=c")


@pytest.mark.parametrize("line", ["", "   ", "# комментарий", "NO_EQUALS_SIGN"])
def test_parse_env_line_rejects_non_pairs(line):
    assert _parse_env_line(line) is None


# --- _load_dotenv: не переопределяет существующее окружение --------------

def test_load_dotenv_sets_and_preserves(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# комментарий\nA=1\nB=2\nBROKEN\n", encoding="utf-8"
    )
    monkeypatch.setenv("A", "existing")
    monkeypatch.delenv("B", raising=False)
    _load_dotenv(env_file)
    import os

    assert os.environ["A"] == "existing"  # setdefault не переопределяет
    assert os.environ["B"] == "2"


def test_load_dotenv_missing_file_is_noop(tmp_path):
    _load_dotenv(tmp_path / "absent.env")  # не должно падать


# --- _env_float / _env_bool ------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [("30", 30.0), ("0.5", 0.5), ("abc", 30.0), (None, 30.0)],
)
def test_env_float_fallback(raw, expected):
    env = {} if raw is None else {"ZVIRT_TIMEOUT": raw}
    assert _env_float(env, "ZVIRT_TIMEOUT", 30.0) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("true", True), ("1", True), ("yes", True), ("on", True),
     ("false", False), ("0", False), ("no", False), ("off", False),
     ("anything", False)],
)
def test_env_bool_variants_extended(raw, expected):
    assert _env_bool({"X": raw}, "X", True) == expected
