"""Smoke tests for the Streamlit UI (no network, no key)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


def _app():
    at = AppTest.from_file(APP, default_timeout=20)
    return at.run()


def test_ui_loads_without_exception():
    assert not _app().exception


def test_sample_button_fills_textarea():
    at = _app()
    at.button(key="sample_btn").click().run()
    assert "Priya Sharma" in at.text_area(key="text_input").value


def test_extract_without_key_shows_error(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "GROQ_API_KEY", None)
    at = _app()
    at.button(key="extract_btn").click().run()
    assert any("No Groq API key" in e.value for e in at.error)
