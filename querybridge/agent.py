"""Provider-neutral orchestration for natural-language database questions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mcp import ClientSession


@dataclass(frozen=True)
class QueryPlan:
    """A provider's proposed SQL query."""

    sql: str


@dataclass(frozen=True)
class ClarificationRequest:
    """A provider's request for more information before planning a query."""

    question: str


@dataclass(frozen=True)
class QueryAnswer:
    """A planned query and the bounded result returned by the MCP server."""

    sql: str
    result: dict[str, object]


class QueryPlanner(Protocol):
    """Interface implemented by a deterministic or model-backed query planner."""

    async def plan(
        self,
        question: str,
        schema: dict[str, dict[str, object]],
    ) -> QueryPlan | ClarificationRequest:
        """Return a read-only query plan or ask the user to clarify."""


async def answer_question(
    session: ClientSession,
    planner: QueryPlanner,
    question: str,
) -> QueryAnswer | ClarificationRequest:
    """Plan from database schema and execute the query through the MCP server."""
    if not question.strip():
        raise ValueError("question must not be empty")

    tables_result = await _call_tool(session, "list_tables", {})
    tables = tables_result.get("result", tables_result)
    if not isinstance(tables, list):
        raise TypeError("list_tables returned an invalid result")

    schema: dict[str, dict[str, object]] = {}
    for table in tables:
        if not isinstance(table, dict) or not isinstance(table.get("name"), str):
            raise TypeError("list_tables returned an invalid table entry")
        name = table["name"]
        schema[name] = await _call_tool(session, "describe_table", {"table_name": name})

    plan = await planner.plan(question, schema)
    if isinstance(plan, ClarificationRequest):
        if not plan.question.strip():
            raise RuntimeError("planner returned an empty clarification request")
        return plan
    if not isinstance(plan, QueryPlan) or not plan.sql.strip():
        raise RuntimeError("planner returned an invalid query plan")

    result = await _call_tool(
        session,
        "query_read_only",
        {"sql": plan.sql, "allowed_tables": list(schema)},
    )
    return QueryAnswer(sql=plan.sql, result=result)


async def _call_tool(
    session: ClientSession,
    name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    response = await session.call_tool(name, arguments)
    if response.isError:
        details = "\n".join(block.text for block in response.content if hasattr(block, "text"))
        raise RuntimeError(f"MCP tool {name} failed: {details}")

    structured_content = getattr(response, "structuredContent", None)
    if not isinstance(structured_content, dict):
        raise TypeError(f"MCP tool {name} returned no structured content")
    return structured_content
