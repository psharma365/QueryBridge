"""Generate a small, deterministic synthetic analytics database."""

from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

DEFAULT_OUTPUT = Path("data/querybridge-sample.db")

_CUSTOMERS = [
    (1, "Northstar Labs", "North", "small_business"),
    (2, "Juniper Health", "West", "enterprise"),
    (3, "Copperfield Market", "South", "small_business"),
    (4, "Bluebird Systems", "East", "mid_market"),
    (5, "Maple Works", "North", "mid_market"),
]

_ORDERS = [
    (1001, 1, "2026-01-05", "completed", 420.00),
    (1002, 2, "2026-01-12", "completed", 1850.00),
    (1003, 3, "2026-01-19", "refunded", 240.00),
    (1004, 4, "2026-02-02", "completed", 960.00),
    (1005, 5, "2026-02-08", "pending", 575.00),
    (1006, 1, "2026-02-17", "completed", 810.00),
    (1007, 2, "2026-03-03", "completed", 1275.00),
    (1008, 3, "2026-03-11", "completed", 390.00),
    (1009, 4, "2026-03-18", "cancelled", 620.00),
    (1010, 5, "2026-04-01", "completed", 1430.00),
    (1011, 1, "2026-04-09", "completed", 690.00),
    (1012, 2, "2026-04-21", "pending", 2150.00),
]


def create_sample_database(
    output: str | Path = DEFAULT_OUTPUT,
    *,
    overwrite: bool = False,
) -> Path:
    """Create synthetic customers and orders, refusing to replace a file by default."""
    path = Path(output).expanduser().resolve()
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing file: {path}. "
            "Pass --force to replace the generated database."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        with closing(sqlite3.connect(temporary_path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE customers (
                    customer_id INTEGER PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    region TEXT NOT NULL,
                    segment TEXT NOT NULL
                );
                CREATE TABLE orders (
                    order_id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
                    ordered_on TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('completed', 'pending', 'refunded', 'cancelled')
                    ),
                    amount REAL NOT NULL CHECK (amount >= 0)
                );
                CREATE INDEX idx_orders_customer_id ON orders(customer_id);
                """
            )
            connection.executemany(
                "INSERT INTO customers VALUES (?, ?, ?, ?)",
                _CUSTOMERS,
            )
            connection.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                _ORDERS,
            )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create QueryBridge's synthetic SQLite analytics database."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"database output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace the output file if it already exists",
    )
    args = parser.parse_args()

    path = create_sample_database(args.output, overwrite=args.force)
    print(f"Created synthetic sample database: {path}")


if __name__ == "__main__":
    main()
