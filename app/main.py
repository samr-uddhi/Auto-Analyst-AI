"""
main.py
-------
FastAPI app exposing the Phase 1 + Append Engine workflow:

  POST /upload         -> first-time upload: infer schema, create table, load data
  POST /append          -> subsequent upload to an existing table: detect drift, append
  GET  /tables/{name}   -> preview a table's data
  GET  /schema/{name}   -> see the inferred schema + transparency log for a table

Run with:  uvicorn main:app --reload
Then visit http://127.0.0.1:8000/docs for interactive API testing.
"""

import io
import sqlite3

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException

from schema_inference import profile_dataset
from db_builder import create_table_from_schema, load_dataframe, append_new_data
from query_engine import answer_question, UnsafeQueryError
from transparency_log import log_event, log_many, get_log
from conversation_memory import add_turn, format_history_for_prompt, clear_history

app = FastAPI(title="AutoAnalyst API", version="0.1.0")

DB_PATH = "autoanalyst.db"

# In-memory record of schema profiles per table, for the transparency log.
# (In a production version this would itself live in the database.)
SCHEMA_REGISTRY: dict[str, dict] = {}


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _read_upload(file: UploadFile) -> pd.DataFrame:
    contents = file.file.read()
    if file.filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(contents))
    elif file.filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(contents))
    raise HTTPException(400, "Unsupported file type — upload a CSV or Excel file.")


@app.post("/upload")
async def upload_dataset(table_name: str, file: UploadFile = File(...)):
    """First-time upload for a new table: profile it, build the table, load data."""
    df = _read_upload(file)
    schema = profile_dataset(df, table_name)

    conn = _get_conn()
    create_sql = create_table_from_schema(conn, schema)
    load_dataframe(conn, df, table_name, if_exists="append")
    conn.close()

    SCHEMA_REGISTRY[table_name] = schema

    log_event(table_name, "schema", f"Table '{table_name}' created from {len(df)} uploaded rows.")
    log_many(table_name, "warning", schema["warnings"])

    return {
        "message": f"Table '{table_name}' created and loaded successfully.",
        "rows_loaded": len(df),
        "schema": schema,
        "sql_used": create_sql,
    }


@app.post("/append")
async def append_dataset(table_name: str, file: UploadFile = File(...)):
    """Incremental upload: append new rows to an existing table, handling
    any new columns automatically."""
    if table_name not in SCHEMA_REGISTRY:
        raise HTTPException(404, f"Table '{table_name}' doesn't exist yet — use /upload first.")

    df = _read_upload(file)
    conn = _get_conn()
    result = append_new_data(conn, table_name, df)
    conn.close()

    log_many(table_name, "append", result["log"])

    return {
        "message": f"Append complete for '{table_name}'.",
        "log": result["log"],
        "schema_drift": result["drift"],
    }


@app.get("/tables/{table_name}")
async def preview_table(table_name: str, limit: int = 20):
    conn = _get_conn()
    try:
        df = pd.read_sql(f'SELECT * FROM "{table_name}" LIMIT {limit}', conn)
    except Exception:
        raise HTTPException(404, f"Table '{table_name}' not found.")
    finally:
        conn.close()
    return df.to_dict(orient="records")


@app.get("/schema/{table_name}")
async def get_schema(table_name: str):
    if table_name not in SCHEMA_REGISTRY:
        raise HTTPException(404, f"No schema recorded for '{table_name}'.")
    return SCHEMA_REGISTRY[table_name]


@app.get("/log/{table_name}")
async def get_transparency_log(table_name: str):
    """Phase 5: every AI decision made about this table, in plain English,
    in chronological order — schema choices, appends, queries, insights,
    and anything blocked for safety."""
    log = get_log(table_name)
    if not log:
        raise HTTPException(404, f"No log entries found for '{table_name}'.")
    return {"table_name": table_name, "entries": log}


@app.post("/query")
async def query_table(table_name: str, question: str, include_insight: bool = True):
    """Phase 3 + 4 + 6: ask a natural-language question about a table and
    get back the generated SQL, the results, and a plain-English insight.
    Follow-up questions ("now break that down by month") are resolved
    using recent conversation history for this table."""
    if table_name not in SCHEMA_REGISTRY:
        raise HTTPException(404, f"Table '{table_name}' doesn't exist yet — use /upload first.")

    schema = SCHEMA_REGISTRY[table_name]
    history_context = format_history_for_prompt(table_name)

    conn = _get_conn()
    try:
        result = answer_question(
            question, schema, conn,
            include_insight=include_insight,
            history_context=history_context,
        )
    except UnsafeQueryError as e:
        log_event(table_name, "warning", f"Blocked an unsafe query for question: '{question}' — {e}")
        raise HTTPException(400, f"Query blocked for safety: {e}")
    finally:
        conn.close()

    add_turn(table_name, question, result["sql_generated"])
    log_event(table_name, "query", f'"{question}" -> {result["sql_generated"]}')
    if include_insight:
        log_event(table_name, "insight", result["insight"])

    return result


@app.post("/reset-conversation/{table_name}")
async def reset_conversation(table_name: str):
    """Clears the follow-up conversation history for a table — the next
    question will be treated as a fresh start, not a continuation."""
    clear_history(table_name)
    return {"message": f"Conversation history cleared for '{table_name}'."}


@app.get("/")
async def root():
    return {"status": "AutoAnalyst API is running", "docs": "/docs"}
