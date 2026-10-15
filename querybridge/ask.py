"""Run one natural-language question using the optional local Ollama planner."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from querybridge.agent import ClarificationRequest, answer_question
from querybridge.ollama_planner import OllamaPlanner
from querybridge.sample_data import DEFAULT_OUTPUT


async def _ask(question: str, database_path: Path, planner: OllamaPlanner) -> None:
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
        answer = await answer_question(session, planner, question)

    if isinstance(answer, ClarificationRequest):
        print(f"Clarification needed: {answer.question}")
        return

    print(f"SQL:\n{answer.sql}")
    print(f"Result:\n{answer.result}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask a question using a local Ollama model and QueryBridge."
    )
    parser.add_argument("question", help="natural-language question about the database")
    parser.add_argument(
        "--database",
        type=Path,
        default=os.environ.get("QUERYBRIDGE_DATABASE_PATH", str(DEFAULT_OUTPUT)),
        help="SQLite database path (defaults to QUERYBRIDGE_DATABASE_PATH or sample database)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("QUERYBRIDGE_OLLAMA_MODEL"),
        help="Ollama model name (defaults to QUERYBRIDGE_OLLAMA_MODEL)",
    )
    parser.add_argument(
        "--ollama-host",
        default=os.environ.get("QUERYBRIDGE_OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama API host",
    )
    args = parser.parse_args()
    if not args.model:
        parser.error("provide --model or set QUERYBRIDGE_OLLAMA_MODEL")
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        parser.error(
            f"database does not exist: {database_path}; create a sample with querybridge-sample"
        )

    asyncio.run(
        _ask(
            args.question,
            database_path,
            OllamaPlanner(model=args.model, host=args.ollama_host),
        )
    )


if __name__ == "__main__":
    main()
