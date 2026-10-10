"""MCP stdio server exposing safe, read-only SQLite tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from querybridge.database import configured_database

mcp = FastMCP("QueryBridge")


@mcp.tool()
def list_tables() -> list[dict[str, str]]:
    """List user tables and views in the configured SQLite database."""
    return configured_database().list_tables()


@mcp.tool()
def describe_table(table_name: str) -> dict[str, object]:
    """Describe columns and primary-key metadata for a table or view."""
    return configured_database().describe_table(table_name)


@mcp.tool()
def query_read_only(sql: str, max_rows: int = 100) -> dict[str, object]:
    """Run one read-only SELECT query and return a bounded result set."""
    return configured_database().query_read_only(sql, max_rows=max_rows)


def main() -> None:
    """Start QueryBridge using the MCP stdio transport."""
    configured_database()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
