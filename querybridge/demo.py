"""Run a short MCP client walkthrough against the configured database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from querybridge.sample_data import DEFAULT_OUTPUT


def _render_result(result: Any) -> str:
    structured_content = getattr(result, "structuredContent", None)
    if structured_content is not None:
        return json.dumps(structured_content, indent=2, ensure_ascii=False)

    text_blocks = [block.text for block in result.content if hasattr(block, "text")]
    return "\n".join(text_blocks) if text_blocks else "(no content)"


async def _run_demo(database_path: Path) -> None:
    environment = os.environ.copy()
    environment["QUERYBRIDGE_DATABASE_PATH"] = str(database_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "querybridge.server"],
        env=environment,
    )

    async with (
        stdio_client(server) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        examples = [
            (
                "Available tables and views",
                "list_tables",
                {},
            ),
            (
                "Orders table schema",
                "describe_table",
                {"table_name": "orders"},
            ),
            (
                "Completed sales by region",
                "query_read_only",
                {
                    "sql": (
                        "SELECT customers.region, ROUND(SUM(orders.amount), 2) AS revenue "
                        "FROM orders JOIN customers USING (customer_id) "
                        "WHERE orders.status = 'completed' "
                        "GROUP BY customers.region ORDER BY revenue DESC"
                    )
                },
            ),
        ]

        for title, tool_name, arguments in examples:
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                raise RuntimeError(f"MCP tool {tool_name} failed: {_render_result(result)}")
            print(f"\n## {title}\n{_render_result(result)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demonstrate QueryBridge tools through an MCP stdio client."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=os.environ.get("QUERYBRIDGE_DATABASE_PATH", str(DEFAULT_OUTPUT)),
        help=(f"SQLite database path (defaults to QUERYBRIDGE_DATABASE_PATH or {DEFAULT_OUTPUT})"),
    )
    args = parser.parse_args()
    if args.database is None:
        parser.error(
            "provide --database or set QUERYBRIDGE_DATABASE_PATH; "
            "create a sample first with `querybridge-sample`"
        )

    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        parser.error(
            f"database does not exist: {database_path}; "
            "create a sample first with `querybridge-sample`"
        )

    asyncio.run(_run_demo(database_path))


if __name__ == "__main__":
    main()
