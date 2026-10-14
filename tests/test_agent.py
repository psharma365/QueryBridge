from __future__ import annotations

from dataclasses import dataclass

import pytest

from querybridge.agent import (
    ClarificationRequest,
    QueryAnswer,
    QueryPlan,
    answer_question,
)


@dataclass
class ToolResponse:
    structuredContent: dict[str, object] | None
    isError: bool = False
    content: list[object] | None = None


class FakeSession:
    def __init__(self, responses: dict[str, ToolResponse]):
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(self, name: str, arguments: dict[str, object]) -> ToolResponse:
        self.calls.append((name, arguments))
        return self.responses[name]


class FixedPlanner:
    def __init__(self, plan: QueryPlan | ClarificationRequest):
        self.response = plan
        self.question: str | None = None
        self.schema: dict[str, dict[str, object]] | None = None

    async def plan(
        self,
        question: str,
        schema: dict[str, dict[str, object]],
    ) -> QueryPlan | ClarificationRequest:
        self.question = question
        self.schema = schema
        return self.response


@pytest.mark.asyncio
async def test_answer_question_uses_schema_and_read_only_query_tool():
    session = FakeSession(
        {
            "list_tables": ToolResponse({"result": [{"name": "orders", "type": "table"}]}),
            "describe_table": ToolResponse(
                {"table": "orders", "columns": [{"name": "amount", "type": "REAL"}]}
            ),
            "query_read_only": ToolResponse(
                {
                    "columns": ["revenue"],
                    "rows": [{"revenue": 12.5}],
                    "row_count": 1,
                    "truncated": False,
                }
            ),
        }
    )
    planner = FixedPlanner(QueryPlan("SELECT SUM(amount) AS revenue FROM orders"))

    answer = await answer_question(session, planner, "What is total revenue?")

    assert answer == QueryAnswer(
        sql="SELECT SUM(amount) AS revenue FROM orders",
        result={
            "columns": ["revenue"],
            "rows": [{"revenue": 12.5}],
            "row_count": 1,
            "truncated": False,
        },
    )
    assert planner.question == "What is total revenue?"
    assert planner.schema == {
        "orders": {
            "table": "orders",
            "columns": [{"name": "amount", "type": "REAL"}],
        }
    }
    assert [name for name, _ in session.calls] == [
        "list_tables",
        "describe_table",
        "query_read_only",
    ]
    assert session.calls[-1][1]["allowed_tables"] == ["orders"]


@pytest.mark.asyncio
async def test_answer_question_returns_clarification_without_querying():
    session = FakeSession(
        {
            "list_tables": ToolResponse({"result": []}),
        }
    )
    planner = FixedPlanner(ClarificationRequest("Which time period do you mean?"))

    answer = await answer_question(session, planner, "How did sales do?")

    assert answer == ClarificationRequest("Which time period do you mean?")
    assert [name for name, _ in session.calls] == ["list_tables"]


@pytest.mark.asyncio
async def test_answer_question_rejects_empty_question_without_calling_tools():
    session = FakeSession({})
    planner = FixedPlanner(QueryPlan("SELECT 1"))

    with pytest.raises(ValueError, match="question must not be empty"):
        await answer_question(session, planner, "  ")

    assert session.calls == []


@pytest.mark.asyncio
async def test_answer_question_rejects_malformed_planner_output():
    session = FakeSession(
        {
            "list_tables": ToolResponse({"result": []}),
        }
    )
    planner = FixedPlanner(None)

    with pytest.raises(RuntimeError, match="invalid query plan"):
        await answer_question(session, planner, "How many orders are there?")

    assert [name for name, _ in session.calls] == ["list_tables"]


@pytest.mark.asyncio
async def test_answer_question_reports_mcp_tool_errors():
    session = FakeSession(
        {
            "list_tables": ToolResponse(
                structuredContent=None,
                isError=True,
                content=[type("Text", (), {"text": "database is unavailable"})()],
            )
        }
    )
    planner = FixedPlanner(QueryPlan("SELECT 1"))

    with pytest.raises(RuntimeError, match="list_tables failed: database is unavailable"):
        await answer_question(session, planner, "How many orders are there?")
