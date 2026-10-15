# QueryBridge

QueryBridge is a provider-neutral foundation for a natural-language data assistant. Its MCP server lets an MCP client inspect a SQLite database and run bounded, read-only queries. The project includes an agent orchestration boundary, but no LLM provider or hosted model integration.

## Current features

- List database tables and views.
- Inspect columns and types for a table or view.
- Execute one read-only SQL query and return at most 100 rows by default.
- Enforce read-only access twice: SQLite opens the database in read-only mode, and an SQLite authorizer rejects non-query operations.
- Stop long-running queries after a configurable server-side timeout (default: 2 seconds).
- Bound SQLite query complexity and reject serialized results larger than 1 MB; binary values are returned as Base64.
- Expose the capabilities as MCP tools over stdio.
- Provide a provider interface that plans queries from a question and schema, with execution delegated to the read-only MCP tool.
- Optionally use a locally running Ollama model as the query planner.

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

## Local demo with synthetic data

Generate a small, deterministic SQLite database containing fictional customers
and orders. The generated database is ignored by Git:

```powershell
querybridge-sample
```

The generator refuses to replace an existing file unless you opt in with
`querybridge-sample --force`. Then run the demo MCP client, which starts the
server over stdio, discovers and calls its tools, and prints the schema and a
regional sales query:

```powershell
querybridge-demo
```

The demo uses `data/querybridge-sample.db` by default. Set
`QUERYBRIDGE_DATABASE_PATH` or provide `--database` to use another SQLite file:

```powershell
querybridge-demo --database C:\path\to\your-read-only-sample.db
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

Query results include column names, returned rows, a row count, and a `truncated`
flag so an agent can tell when it received only part of the result set.
The `query_read_only` tool accepts an optional `allowed_tables` list; the agent
boundary supplies the names it discovered before planning. This limits a
planner-generated query but is not user authentication or a per-user access
control mechanism.

## Agent boundary and data flow

`querybridge.agent` defines a `QueryPlanner` interface and an orchestration
function for MCP clients. A planner receives the user's question and table
schema, then returns a SQL plan or asks for clarification. QueryBridge sends a
plan only to `query_read_only`; the server remains responsible for enforcing
read-only access and result limits. The agent also passes the inspected table
names as an allowlist, which the SQLite authorizer applies during query
execution. The orchestration returns the SQL and bounded result as evidence
rather than asking a model to invent a summary.

There is no model provider configured by default, and the tests use a
deterministic planner fixture. If a hosted planner is added later, its provider
will receive the user's question and database schema. This flow does not send
query results or database rows to the planner. Treat questions and schema as
potentially sensitive before configuring any external provider; provider-side
logging and retention will depend on that provider.

## Optional local Ollama planner

QueryBridge can use Ollama's local chat API without adding a Python provider
dependency. This option requires Ollama and a model installed locally; neither
is downloaded or started automatically. For example, after installing Ollama
and pulling a model that supports structured JSON output:

```powershell
ollama pull qwen2.5:3b
$env:QUERYBRIDGE_OLLAMA_MODEL = "qwen2.5:3b"
querybridge-ask "What is completed revenue by region?"
```

The command uses `data/querybridge-sample.db` by default. Create it first with
`querybridge-sample`, or pass `--database` to use another file. Override the
Ollama API host with `QUERYBRIDGE_OLLAMA_HOST` or `--ollama-host`; the default
is `http://localhost:11434`. If you choose a remote host, the user's question
and database schema will be sent to it. Query results are not sent to the model.
The model's SQL is still subject to the read-only SQLite authorizer, discovered
table allowlist, timeout, and result limits.

Model memory, speed, and hardware requirements depend on the chosen model and
quantization; consult the selected model's Ollama library page for its download
size and requirements. Small quantized models can run on CPU, though generation
may be slower than on supported GPU hardware. The small example is a starting
point, not a guarantee for every machine. No model/API calls are required for
tests or for using the MCP server without `querybridge-ask`.

## Safety scope

This project is deliberately limited to local SQLite and has no concrete LLM
provider, user authentication, per-user authorization, cloud deployment, or
complete SQL cost/resource budget. A planner's SQL is untrusted input; the
server-side read-only authorizer and query bounds remain essential. The query
timeout and row cap are safeguards, not a substitute for OS-level resource
isolation. Do not point it at sensitive data or expose it to untrusted clients.

The project remains local-only; adding a real model provider or cloud deployment
requires separate design and cost decisions.

## Deterministic agent evaluation

`tests/fixtures/agent_evaluation.json` contains versioned planner fixtures for a
correct aggregate query, an ambiguous question, and an unsafe write attempt.
Run them against the generated synthetic database and actual MCP stdio server:

```powershell
python -m pytest tests/test_evaluation.py
```

The checks separately assert result correctness, clarification behavior, and
write rejection. These fixtures measure regression behavior for a deterministic
planner; they are not an accuracy benchmark for an LLM.

## Development

```powershell
python -m pytest
ruff check .
ruff format --check .
```
