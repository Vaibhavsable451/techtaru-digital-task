"""Tests run offline: the Groq client is mocked, no API key needed."""
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from groq import RateLimitError

from app import extractor
from app.extractor import (EmptyInputError, NoDataFoundError, RateLimitedError,
                           UpstreamError, extract)
from app.main import app
from app.schemas import DocType


class FakeClient:
    """Returns queued replies (str) or raises queued exceptions."""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))])


def test_resume_ok():
    c = FakeClient(json.dumps({"full_name": "Priya", "skills": ["Python"]}))
    data, w = extract("Priya knows Python", DocType.resume, client=c)
    assert data["full_name"] == "Priya" and data["skills"] == ["Python"] and w == []


def test_empty_input():
    with pytest.raises(EmptyInputError):
        extract("   ", DocType.resume, client=FakeClient())


def test_too_long_input(monkeypatch):
    monkeypatch.setattr(extractor.config, "MAX_INPUT_CHARS", 10)
    with pytest.raises(EmptyInputError):
        extract("x" * 11, DocType.resume, client=FakeClient())


def test_retry_on_bad_json_then_success():
    c = FakeClient("not json", json.dumps({"full_name": "A"}))
    data, _ = extract("A", DocType.resume, client=c)
    assert data["full_name"] == "A" and c.calls == 2


def test_two_bad_outputs_fail():
    with pytest.raises(UpstreamError):
        extract("A", DocType.resume, client=FakeClient("bad", "still bad"))


def test_no_data_found():
    with pytest.raises(NoDataFoundError):
        extract("hello world", DocType.invoice, client=FakeClient("{}"))


def test_rate_limit_message():
    req = httpx.Request("POST", "https://api.groq.com")
    err = RateLimitError("429", response=httpx.Response(429, request=req), body=None)
    with pytest.raises(RateLimitedError):
        extract("A", DocType.resume, client=FakeClient(err))


def test_invoice_math_warning():
    bad = {"invoice_number": "1", "subtotal": 100, "tax": 18, "total": 999,
           "line_items": [{"total": 100}]}
    _, warnings = extract("inv", DocType.invoice, client=FakeClient(json.dumps(bad)))
    assert any("total is 999" in w for w in warnings)


def test_api_missing_key(monkeypatch):
    monkeypatch.setattr(extractor.config, "GROQ_API_KEY", None)
    r = TestClient(app).post("/extract", json={"text": "hi", "doc_type": "resume"})
    assert r.status_code == 500 and "GROQ_API_KEY" in r.json()["error"]


def test_api_bad_doc_type():
    r = TestClient(app).post("/extract", json={"text": "hi", "doc_type": "poem"})
    assert r.status_code == 422


def test_gpt_oss_gets_low_reasoning_effort(monkeypatch):
    monkeypatch.setattr(extractor.config, "GROQ_MODEL", "openai/gpt-oss-120b")
    assert extractor._model_options() == {"extra_body": {"reasoning_effort": "low"}}
    monkeypatch.setattr(extractor.config, "GROQ_MODEL", "llama-3.3-70b-versatile")
    assert extractor._model_options() == {}
