"""Read-only SQLite operations used by QueryBridge MCP tools."""

from __future__ import annotations

import base64
import json
import math
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

DEFAULT_MAX_ROWS = 100
HARD_MAX_ROWS = 500
DEFAULT_QUERY_TIMEOUT_SECONDS = 2.0
MAX_RESULT_BYTES = 1_000_000

_QUERY_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


class DatabaseConfigurationError(ValueError):
    """Raised when the configured SQLite database cannot be opened safely."""


class QueryValidationError(ValueError):
    """Raised when a request is not a single read-only query."""


def _database_path() -> Path:
    configured_path = os.environ.get("QUERYBRIDGE_DATABASE_PATH")
    if not configured_path:
        raise DatabaseConfigurationError(
            "Set QUERYBRIDGE_DATABASE_PATH to an existing SQLite database file."
        )

    path = Path(configured_path).expanduser().resolve()
    if not path.is_file():
        raise DatabaseConfigurationError(f"SQLite database file does not exist: {path}")
    return path


class SQLiteDatabase:
    """A small SQLite adapter that never opens a writable connection."""

    def __init__(
        self,
        path: str | Path,
        *,
        query_timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise DatabaseConfigurationError(f"SQLite database file does not exist: {self.path}")
        if query_timeout_seconds <= 0:
            raise ValueError("query_timeout_seconds must be greater than zero")
        self.query_timeout_seconds = query_timeout_seconds

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{self.path.as_uri()}?mode=ro",
            uri=True,
            timeout=self.query_timeout_seconds,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 256_000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 64_000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 100)
        connection.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 50)
        connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        connection.set_authorizer(self._authorize_query)
        return connection

    @staticmethod
    def _authorize_query(
        action: int,
        first_argument: str | None,
        second_argument: str | None,
        _database_name: str | None,
        _trigger_name: str | None,
    ) -> int:
        if action in _QUERY_ACTIONS:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA and first_argument == "table_info":
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def list_tables(self) -> list[dict[str, str]]:
        """Return user tables and views without exposing SQLite internals."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT name, type
                FROM sqlite_schema
                WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return [{"name": row["name"], "type": row["type"]} for row in rows]

    def describe_table(self, table_name: str) -> dict[str, Any]:
        """Return column metadata for an existing table or view."""
        if not table_name.strip():
            raise QueryValidationError("table_name must not be empty")

        with closing(self._connect()) as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM sqlite_schema
                WHERE name = ? AND type IN ('table', 'view')
                    AND name NOT LIKE 'sqlite_%'
                """,
                (table_name,),
            ).fetchone()
            if exists is None:
                raise QueryValidationError(f"Unknown table or view: {table_name}")

            escaped_name = table_name.replace('"', '""')
            columns = connection.execute(f'PRAGMA table_info("{escaped_name}")').fetchall()

        return {
            "table": table_name,
            "columns": [
                {
                    "name": column["name"],
                    "type": column["type"],
                    "not_null": bool(column["notnull"]),
                    "primary_key": bool(column["pk"]),
                }
                for column in columns
            ],
        }

    def query_read_only(
        self,
        sql: str,
        *,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> dict[str, Any]:
        """Execute one read-only query and return no more than the configured row cap."""
        if not sql or not sql.strip():
            raise QueryValidationError("sql must not be empty")
        if not 1 <= max_rows <= HARD_MAX_ROWS:
            raise QueryValidationError(f"max_rows must be between 1 and {HARD_MAX_ROWS}")
        if _first_keyword(sql) not in {"select", "with"}:
            raise QueryValidationError("Only SELECT queries are allowed")

        started_at = time.monotonic()
        deadline = started_at + self.query_timeout_seconds
        with closing(self._connect()) as connection:
            connection.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
            try:
                cursor = connection.execute(sql)
                rows = cursor.fetchmany(max_rows + 1)
            except sqlite3.OperationalError as error:
                if "interrupted" in str(error).lower():
                    raise TimeoutError(
                        f"Query exceeded the {self.query_timeout_seconds:g}s time limit"
                    ) from error
                raise QueryValidationError(f"Query could not be executed: {error}") from error
            except sqlite3.DatabaseError as error:
                raise QueryValidationError(f"Query could not be executed: {error}") from error

        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        result = {
            "columns": [column[0] for column in cursor.description or ()],
            "rows": [{key: _json_value(value) for key, value in dict(row).items()} for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_RESULT_BYTES:
            raise QueryValidationError(
                f"Query result exceeds the {MAX_RESULT_BYTES}-byte response limit; "
                "request fewer rows or smaller columns"
            )
        return result


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _first_keyword(sql: str) -> str:
    """Read the leading SQL keyword, skipping whitespace and leading comments."""
    index = 0
    while index < len(sql):
        while index < len(sql) and sql[index].isspace():
            index += 1
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            if newline == -1:
                return ""
            index = newline + 1
            continue
        if sql.startswith("/*", index):
            end_comment = sql.find("*/", index + 2)
            if end_comment == -1:
                return ""
            index = end_comment + 2
            continue
        break

    end = index
    while end < len(sql) and (sql[end].isalpha() or sql[end] == "_"):
        end += 1
    return sql[index:end].lower()


def configured_database() -> SQLiteDatabase:
    """Create a database adapter using the configured path."""
    return SQLiteDatabase(_database_path())
