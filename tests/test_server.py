from __future__ import annotations

import os
import sqlite3
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from querybridge.agent import QueryPlan, answer_question


class DeterministicPlanner:
    async def plan(self, question, schema):
        assert question == "What is the total order amount?"
        assert "orders" in schema
        return QueryPlan("SELECT SUM(amount) AS total FROM orders")


@pytest.mark.asyncio
async def test_mcp_server_discovers_tools_and_executes_read_query(tmp_path):
    database_path = tmp_path / "analytics.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount REAL)")
        connection.execute("INSERT INTO orders (amount) VALUES (12.5)")

    server_environment = os.environ.copy()
    server_environment["QUERYBRIDGE_DATABASE_PATH"] = str(database_path)
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "querybridge.server"],
        env=server_environment,
    )

    async with (
        stdio_client(server_params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        tool_names = {tool.name for tool in tools.tools}

        assert {"list_tables", "describe_table", "query_read_only"} <= tool_names

        result = await session.call_tool(
            "query_read_only",
            {"sql": "SELECT amount FROM orders"},
        )
        assert result.isError is False
        assert "12.5" in str(result.content)

        answer = await answer_question(
            session,
            DeterministicPlanner(),
            "What is the total order amount?",
        )
        assert answer.sql == "SELECT SUM(amount) AS total FROM orders"
        assert answer.result["rows"] == [{"total": 12.5}]
        assert answer.result["row_count"] == 1
