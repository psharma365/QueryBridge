from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from querybridge import ollama_planner
from querybridge.agent import ClarificationRequest, QueryPlan
from querybridge.ollama_planner import OllamaPlanner


@pytest.mark.asyncio
async def test_ollama_planner_builds_local_structured_request(monkeypatch):
    planner = OllamaPlanner("test-model")
    captured: dict[str, object] = {}

    def fake_post_json(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"message": {"content": json.dumps({"action": "query", "sql": "SELECT 1"})}}

    monkeypatch.setattr(planner, "_post_json", fake_post_json)

    plan = await planner.plan(
        "How many orders are there?",
        {"orders": {"columns": [{"name": "id", "type": "INTEGER"}]}},
    )

    assert plan == QueryPlan("SELECT 1")
    assert captured["url"] == "http://localhost:11434/api/chat"
    payload = captured["payload"]
    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert "untrusted data" in payload["messages"][0]["content"]
    assert json.loads(payload["messages"][1]["content"]) == {
        "question": "How many orders are there?",
        "schema": {"orders": {"columns": [{"name": "id", "type": "INTEGER"}]}},
    }


@pytest.mark.asyncio
async def test_ollama_planner_returns_clarification(monkeypatch):
    planner = OllamaPlanner("test-model")
    monkeypatch.setattr(
        planner,
        "_post_json",
        lambda _url, _payload: {
            "message": {
                "content": json.dumps(
                    {
                        "action": "clarify",
                        "sql": "",
                        "clarification_question": "Which time period?",
                    }
                )
            }
        },
    )

    assert await planner.plan("How did sales do?", {}) == ClarificationRequest("Which time period?")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "error", "message"),
    [
        ('{"action": "query", "sql": ""}', ValueError, "empty SQL query"),
        ('{"action": "clarify", "clarification_question": ""}', ValueError, "empty clarification"),
        ("not json", RuntimeError, "invalid JSON"),
        ('{"action": "other"}', ValueError, "unsupported"),
        ("[]", TypeError, "JSON object"),
    ],
)
async def test_ollama_planner_rejects_malformed_output(monkeypatch, content, error, message):
    planner = OllamaPlanner("test-model")
    monkeypatch.setattr(
        planner,
        "_post_json",
        lambda _url, _payload: {"message": {"content": content}},
    )

    with pytest.raises(error, match=message):
        await planner.plan("question", {})


def test_ollama_planner_requires_model_name(monkeypatch):
    monkeypatch.delenv("QUERYBRIDGE_OLLAMA_MODEL", raising=False)

    with pytest.raises(ValueError, match="QUERYBRIDGE_OLLAMA_MODEL"):
        OllamaPlanner()


def test_ollama_planner_posts_json_to_configured_local_api(monkeypatch):
    planner = OllamaPlanner("test-model", host="http://localhost:1234")
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"message": {"content": "{}"}}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(ollama_planner, "urlopen", fake_urlopen)

    result = planner._post_json(
        "http://localhost:1234/api/chat",
        {"model": "test-model"},
    )

    assert result == {"message": {"content": "{}"}}
    assert captured == {
        "url": "http://localhost:1234/api/chat",
        "method": "POST",
        "payload": {"model": "test-model"},
        "timeout": 60,
    }


def test_ollama_planner_reports_connection_failures(monkeypatch):
    planner = OllamaPlanner("test-model")

    def fail_urlopen(_request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(ollama_planner, "urlopen", fail_urlopen)

    with pytest.raises(RuntimeError, match="Could not reach Ollama"):
        planner._post_json(
            "http://localhost:11434/api/chat",
            {"model": "test-model"},
        )
