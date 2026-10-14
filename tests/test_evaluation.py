from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from querybridge.agent import ClarificationRequest, QueryPlan, answer_question
from querybridge.sample_data import create_sample_database

_CASES_PATH = Path(__file__).parent / "fixtures" / "agent_evaluation.json"


class FixturePlanner:
    def __init__(self, response: QueryPlan | ClarificationRequest):
        self.response = response

    async def plan(self, question, schema):
        assert question.strip()
        assert schema
        return self.response


def _load_cases() -> list[dict[str, object]]:
    with _CASES_PATH.open(encoding="utf-8") as cases_file:
        cases = json.load(cases_file)
    if not isinstance(cases, list):
        raise TypeError("evaluation cases must be a JSON array")
    return cases


@pytest.mark.asyncio
async def test_deterministic_agent_evaluation_cases(tmp_path):
    database_path = create_sample_database(tmp_path / "sample.db")
    environment = os.environ.copy()
    environment["QUERYBRIDGE_DATABASE_PATH"] = str(database_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "querybridge.server"],
        env=environment,
    )
    counts = {
        "query_cases": 0,
        "correct_query_results": 0,
        "clarification_cases": 0,
        "unsafe_query_cases": 0,
        "unsafe_queries_rejected": 0,
    }

    async with (
        stdio_client(server) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        for case in _load_cases():
            expected = case["expected"]
            kind = expected["type"]
            if kind == "query":
                counts["query_cases"] += 1
                planner_response = QueryPlan(expected["sql"])
            elif kind == "clarification":
                counts["clarification_cases"] += 1
                planner_response = ClarificationRequest(expected["question"])
            elif kind == "rejected":
                counts["unsafe_query_cases"] += 1
                planner_response = QueryPlan(expected["sql"])
            else:
                raise ValueError(f"Unknown evaluation case type: {kind}")

            planner = FixturePlanner(planner_response)
            if kind == "query":
                answer = await answer_question(session, planner, case["question"])
                assert answer.sql == expected["sql"], case["id"]
                assert answer.result["rows"] == expected["rows"], case["id"]
                counts["correct_query_results"] += 1
            elif kind == "clarification":
                answer = await answer_question(session, planner, case["question"])
                assert answer == planner_response, case["id"]
            else:
                with pytest.raises(RuntimeError, match="query_read_only failed"):
                    await answer_question(session, planner, case["question"])
                counts["unsafe_queries_rejected"] += 1

    assert counts == {
        "query_cases": 1,
        "correct_query_results": 1,
        "clarification_cases": 1,
        "unsafe_query_cases": 1,
        "unsafe_queries_rejected": 1,
    }
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 12
