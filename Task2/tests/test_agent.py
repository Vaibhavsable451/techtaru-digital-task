"""Offline tests: no real network or OpenAI key needed."""
import json
from types import SimpleNamespace as NS
from unittest.mock import patch

from app import tools
from app.agent import run_agent


def fc(name, args, cid="c1"):
    return NS(type="function_call", name=name, arguments=json.dumps(args), call_id=cid)


class FakeClient:
    """Scripted stand-in for OpenAI: first reply = tool call, second = final text."""
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.responses = self

    def create(self, **kw):
        self.calls.append(kw)
        out = self.script.pop(0)
        text = out[0].text if out and out[0].type == "message" else ""
        return NS(output=out, output_text=text)


def msg(text):
    return NS(type="message", text=text)


def test_empty_input():
    assert run_agent("") == "Please enter a question."
    assert run_agent("   ") == "Please enter a question."


def test_no_tool_for_greeting():
    c = FakeClient([[msg("Hello!")]])
    assert run_agent("Hello", client=c) == "Hello!"
    assert len(c.calls) == 1


def test_weather_routes_to_tool_and_back_to_llm():
    c = FakeClient([[fc("get_weather", {"city": "Pune"})], [msg("It is 27C in Pune.")]])
    fake = {"success": True, "city": "Pune", "temperature_c": 27}
    with patch.dict(tools.TOOL_REGISTRY, {"get_weather": lambda city: fake}):
        assert run_agent("Weather in Pune?", client=c) == "It is 27C in Pune."
    sent = c.calls[1]["input"]
    assert any(isinstance(i, dict) and i.get("type") == "function_call_output" for i in sent)


def test_unknown_tool():
    assert tools.execute_tool("hack", {})["success"] is False


def test_bad_tool_args():
    assert tools.execute_tool("get_weather", {"wrong": 1})["success"] is False


def test_empty_city_and_symbol():
    assert tools.get_weather("  ")["error"] == "City name cannot be empty."
    assert tools.get_stock_price("")["success"] is False


def test_demo_stock_and_unknown_symbol(monkeypatch):
    monkeypatch.setenv("STOCK_USE_DEMO", "true")
    assert tools.get_stock_price("aapl")["price"] == 225.50
    assert tools.get_stock_price("XYZ")["success"] is False
    assert tools.calculate_stock_value("AAPL", 2)["total_value"] == 451.0
    assert tools.calculate_stock_value("AAPL", -1)["success"] is False


def test_rate_limit_handled():
    class R:
        status_code = 429
    with patch("app.tools.requests.get", return_value=R()):
        assert "rate limit" in tools.get_weather("Pune")["error"].lower()


def test_timeout_handled():
    import requests
    with patch("app.tools.requests.get", side_effect=requests.exceptions.Timeout):
        assert "timed out" in tools.get_weather("Pune")["error"]
