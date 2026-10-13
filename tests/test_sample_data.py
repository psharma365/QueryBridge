from __future__ import annotations

import sqlite3

import pytest

from querybridge.sample_data import create_sample_database


def test_sample_database_contains_deterministic_synthetic_data(tmp_path):
    path = create_sample_database(tmp_path / "sample.db")

    with sqlite3.connect(path) as connection:
        customers = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        orders = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        regional_sales = connection.execute(
            """
            SELECT customers.region, ROUND(SUM(orders.amount), 2)
            FROM orders JOIN customers USING (customer_id)
            WHERE orders.status = 'completed'
            GROUP BY customers.region
            ORDER BY 2 DESC
            """
        ).fetchall()

    assert customers == 5
    assert orders == 12
    assert regional_sales == [
        ("North", 3350.0),
        ("West", 3125.0),
        ("East", 960.0),
        ("South", 390.0),
    ]


def test_sample_database_refuses_to_overwrite_without_explicit_flag(tmp_path):
    path = create_sample_database(tmp_path / "sample.db")
    original_bytes = path.read_bytes()

    with pytest.raises(FileExistsError, match="--force"):
        create_sample_database(path)

    assert path.read_bytes() == original_bytes


def test_sample_database_can_be_recreated_explicitly(tmp_path):
    path = create_sample_database(tmp_path / "sample.db")

    recreated = create_sample_database(path, overwrite=True)

    assert recreated == path
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 12
