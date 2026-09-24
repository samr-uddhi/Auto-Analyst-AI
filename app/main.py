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


@app.post("/query")
async def query_table(table_name: str, question: str):
    """Phase 3: ask a natural-language question about a table and get
    back the generated SQL + results."""
    if table_name not in SCHEMA_REGISTRY:
        raise HTTPException(404, f"Table '{table_name}' doesn't exist yet — use /upload first.")

    schema = SCHEMA_REGISTRY[table_name]
    conn = _get_conn()
    try:
        result = answer_question(question, schema, conn)
    except UnsafeQueryError as e:
        raise HTTPException(400, f"Query blocked for safety: {e}")
    finally:
        conn.close()

    return result


@app.get("/")
async def root():
    return {"status": "AutoAnalyst API is running", "docs": "/docs"}
