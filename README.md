# QueryBridge

QueryBridge is the foundation for a secure natural-language data assistant. This first milestone provides an MCP server that lets an MCP-compatible AI client inspect a SQLite database and run bounded, read-only queries. The natural-language agent is a separate planned component; this server does not call an LLM.

## Current features

- List database tables and views.
- Inspect columns and types for a table or view.
- Execute one read-only SQL query and return at most 100 rows by default.
- Enforce read-only access twice: SQLite opens the database in read-only mode, and an SQLite authorizer rejects non-query operations.
- Stop long-running queries after a configurable server-side timeout (default: 2 seconds).
- Expose the capabilities as MCP tools over stdio.

## Requirements

- Python 3.11 or newer
- An SQLite database file readable by the current user
- An MCP-compatible client

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Set the path to an existing database:

```powershell
$env:QUERYBRIDGE_DATABASE_PATH = "C:\path\to\sample.db"
```

Start the MCP server:

```powershell
querybridge
```

For local development without installing the command:

```powershell
python -m querybridge.server
```

Configure your MCP client to launch the command in the project environment. For example:

```json
{
  "mcpServers": {
    "querybridge": {
      "command": "C:\\path\\to\\Querybridge\\.venv\\Scripts\\querybridge.exe",
      "env": {
        "QUERYBRIDGE_DATABASE_PATH": "C:\\path\\to\\sample.db"
      }
    }
  }
}
```

## Available MCP tools

| Tool | Purpose |
| --- | --- |
| `list_tables` | List accessible tables and views. |
| `describe_table` | Return column names, declared types, and primary-key metadata. |
| `query_read_only` | Run a read-only SQL query with a bounded result count. |

## Safety scope

This milestone is deliberately limited to local SQLite. It does not yet implement the LLM agent, user authentication, per-user authorization, cloud deployment, or a complete SQL cost/resource budget. The query timeout and row cap are safeguards, not a substitute for OS-level resource isolation. Do not point it at sensitive data or expose it to untrusted clients.

The next milestones can add a natural-language agent, an evaluation set, and cloud deployment after the MCP data-access layer is tested.

## Development

```powershell
python -m pytest
ruff check .
ruff format --check .
```
