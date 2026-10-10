from __future__ import annotations

import sqlite3

import pytest

from querybridge.database import QueryValidationError, SQLiteDatabase


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "analytics.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE orders "
            "(id INTEGER PRIMARY KEY, region TEXT NOT NULL, amount REAL NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO orders (region, amount) VALUES (?, ?)",
            [("west", 10.5), ("east", 20.0), ("west", 7.5)],
        )
    return path


def test_list_tables(database_path):
    database = SQLiteDatabase(database_path)

    assert database.list_tables() == [{"name": "orders", "type": "table"}]


def test_describe_table(database_path):
    database = SQLiteDatabase(database_path)

    result = database.describe_table("orders")

    assert result["columns"] == [
        {"name": "id", "type": "INTEGER", "not_null": False, "primary_key": True},
        {"name": "region", "type": "TEXT", "not_null": True, "primary_key": False},
        {"name": "amount", "type": "REAL", "not_null": True, "primary_key": False},
    ]


def test_query_returns_rows_and_column_names(database_path):
    database = SQLiteDatabase(database_path)

    result = database.query_read_only("SELECT region, amount FROM orders ORDER BY amount DESC")

    assert result == {
        "columns": ["region", "amount"],
        "rows": [
            {"region": "east", "amount": 20.0},
            {"region": "west", "amount": 10.5},
            {"region": "west", "amount": 7.5},
        ],
        "row_count": 3,
        "truncated": False,
    }


def test_query_enforces_result_cap(database_path):
    database = SQLiteDatabase(database_path)

    result = database.query_read_only("SELECT * FROM orders ORDER BY id", max_rows=2)

    assert result["row_count"] == 2
    assert result["truncated"] is True


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "UPDATE orders SET amount = 0",
        "INSERT INTO orders (region, amount) VALUES ('north', 1)",
        "DROP TABLE orders",
        "PRAGMA table_info(orders)",
        "SELECT * FROM orders; DELETE FROM orders",
    ],
)
def test_rejects_non_read_only_or_multiple_statements(database_path, sql):
    database = SQLiteDatabase(database_path)

    with pytest.raises(QueryValidationError):
        database.query_read_only(sql)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 3


def test_rejects_unknown_table(database_path):
    database = SQLiteDatabase(database_path)

    with pytest.raises(QueryValidationError, match="Unknown table"):
        database.describe_table("missing")


def test_enforces_maximum_row_limit(database_path):
    database = SQLiteDatabase(database_path)

    with pytest.raises(QueryValidationError, match="max_rows"):
        database.query_read_only("SELECT * FROM orders", max_rows=501)
