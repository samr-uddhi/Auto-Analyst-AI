"""
query_engine.py
----------------
Phase 3: Natural language -> SQL -> results.

Takes a plain-English question + the table's schema, asks Claude to
generate the SQL, validates it's safe to run (read-only, single
statement, no destructive keywords), executes it, and returns the
results alongside the SQL used (for transparency).

Requires an Anthropic API key set as the environment variable
ANTHROPIC_API_KEY (see .env.example).
"""

import os
import re
import sqlite3
import json

import pandas as pd
from anthropic import Anthropic

from insight_generator import generate_insight


# ---- Safety: only ever allow read-only, single-statement SQL ----
FORBIDDEN_KEYWORDS = [
    "drop", "delete", "update", "insert", "alter", "truncate",
    "create", "replace", "attach", "detach", "pragma", "vacuum",
]


class UnsafeQueryError(Exception):
    pass


def _build_schema_context(schema: dict) -> str:
    """Turns a schema profile (from schema_inference.py) into a compact
    description the LLM can reason about."""
    lines = [f'Table: "{schema["table_name"]}"']
    for col in schema["columns"]:
        lines.append(f'  - "{col["name"]}" ({col["sql_type"]})')
    if schema.get("primary_key"):
        lines.append(f'Primary key: "{schema["primary_key"]}"')
    return "\n".join(lines)


def _extract_sql(raw_response: str) -> str:
    """Pulls the SQL statement out of the model's response, whether it's
    wrapped in a ```sql code block or returned as plain text."""
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", raw_response, re.DOTALL | re.IGNORECASE)
    sql = fenced.group(1).strip() if fenced else raw_response.strip()
    return sql.rstrip(";").strip()


def _validate_sql(sql: str) -> None:
    """Raises UnsafeQueryError if the SQL isn't a single, read-only SELECT."""
    lowered = sql.lower()

    if ";" in sql.rstrip(";"):
        raise UnsafeQueryError("Multiple statements are not allowed.")

    if not lowered.strip().startswith("select"):
        raise UnsafeQueryError("Only SELECT queries are allowed.")

    for word in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{word}\b", lowered):
            raise UnsafeQueryError(f"Query contains a forbidden keyword: '{word}'.")


def generate_sql(question: str, schema: dict, client: Anthropic | None = None,
                  history_context: str = "") -> str:
    """Calls Claude to turn a natural-language question into SQL for the
    given schema. Returns validated SQL (raises UnsafeQueryError if the
    model returns something unsafe).

    `history_context` (optional) is recent conversation history, so
    follow-up questions like "now break that down by month" can be
    resolved against the previous query instead of standing alone."""
    client = client or Anthropic()
    schema_context = _build_schema_context(schema)

    system_prompt = (
        "You are a SQL generator for a SQLite database. Given a table schema "
        "and a natural-language question, respond with ONLY the SQL query "
        "needed to answer it — no explanation, no markdown, just the raw SQL. "
        "Always use SELECT statements only. Never modify data. "
        "Use exact column and table names as given, wrapped in double quotes. "
        "If conversation history is provided and the question refers to a "
        "previous result (e.g. 'that', 'those', 'now also show...', 'break "
        "that down by...'), use the most recent query as context to build "
        "on rather than starting over."
    )

    prompt_parts = [schema_context]
    if history_context:
        prompt_parts.append(history_context)
    prompt_parts.append(f"Question: {question}\n\nSQL query:")
    user_prompt = "\n\n".join(prompt_parts)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    sql = _extract_sql(raw_text)
    _validate_sql(sql)
    return sql


def run_query(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    """Executes a pre-validated SQL statement and returns results as a DataFrame."""
    return pd.read_sql(sql, conn)


def answer_question(question: str, schema: dict, conn: sqlite3.Connection,
                     client: Anthropic | None = None, include_insight: bool = True,
                     history_context: str = "") -> dict:
    """Full pipeline: question -> SQL -> results -> plain-English insight,
    with everything the transparency log needs. Pass `history_context`
    (from conversation_memory.format_history_for_prompt) to let this
    question build on a previous one."""
    client = client or Anthropic()
    sql = generate_sql(question, schema, client=client, history_context=history_context)
    results = run_query(conn, sql)
    records = results.to_dict(orient="records")

    output = {
        "question": question,
        "sql_generated": sql,
        "row_count": len(results),
        "results": records,
    }

    if include_insight:
        output["insight"] = generate_insight(question, sql, records, client=client)

    return output


if __name__ == "__main__":
    # Offline test of the extraction + validation logic (no API call needed)
    test_cases = [
        "```sql\nSELECT * FROM \"orders\" WHERE amount > 100;\n```",
        "SELECT region, SUM(amount) FROM \"orders\" GROUP BY region",
        "DROP TABLE orders;",                       # should fail validation
        "SELECT * FROM orders; DELETE FROM orders;",  # should fail validation
    ]

    for raw in test_cases:
        sql = _extract_sql(raw)
        try:
            _validate_sql(sql)
            print(f"SAFE:   {sql}")
        except UnsafeQueryError as e:
            print(f"BLOCKED: {sql!r} -> {e}")
