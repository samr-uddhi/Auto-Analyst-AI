"""
db_builder.py
-------------
Takes a schema profile (from schema_inference.py) and:
- dynamically creates the matching SQLite table (CREATE TABLE ... auto-generated)
- loads the dataframe into it
- on future uploads to the same table, detects new columns (schema drift)
  and either adds them or flags a conflict, then appends new rows

This is Phase 1 + the beginning of the Append Engine (Phase 2).
"""

import sqlite3
import pandas as pd


def _sql_column_def(col: dict) -> str:
    return f'"{col["name"]}" {col["sql_type"]}'


def create_table_from_schema(conn: sqlite3.Connection, schema: dict) -> str:
    """Builds and executes a CREATE TABLE statement from a schema profile.
    Returns the SQL statement used (for the transparency log)."""
    table = schema["table_name"]
    col_defs = [_sql_column_def(c) for c in schema["columns"]]

    if schema["primary_key"]:
        # Mark the detected primary key column
        col_defs = [
            f'"{c["name"]}" {c["sql_type"]} PRIMARY KEY'
            if c["name"] == schema["primary_key"] else _sql_column_def(c)
            for c in schema["columns"]
        ]
    else:
        col_defs.insert(0, '"row_id" INTEGER PRIMARY KEY AUTOINCREMENT')

    sql = f'CREATE TABLE IF NOT EXISTS "{table}" (\n  ' + ",\n  ".join(col_defs) + "\n);"
    conn.execute(sql)
    conn.commit()
    return sql


def load_dataframe(conn: sqlite3.Connection, df: pd.DataFrame, table_name: str, if_exists="append"):
    """Loads a dataframe into an existing table. `if_exists='append'` is the
    default because the append engine assumes the table was already created
    by create_table_from_schema()."""
    df.to_sql(table_name, conn, if_exists=if_exists, index=False)


def detect_schema_drift(conn: sqlite3.Connection, table_name: str, new_df: pd.DataFrame) -> dict:
    """Compares an incoming dataframe's columns against the existing table's
    columns. Returns which columns are new (schema drift) vs matching,
    so the caller can decide whether to auto-ALTER the table or flag it."""
    existing_cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")')}
    incoming_cols = set(new_df.columns)

    new_columns = incoming_cols - existing_cols
    missing_columns = existing_cols - incoming_cols - {"row_id"}

    return {
        "new_columns": list(new_columns),
        "missing_columns": list(missing_columns),
        "is_compatible": len(new_columns) == 0,
    }


def append_new_data(conn: sqlite3.Connection, table_name: str, new_df: pd.DataFrame) -> dict:
    """Handles an incremental upload: detects drift, auto-adds new columns
    if needed, appends the rows, and returns a plain-English log entry."""
    drift = detect_schema_drift(conn, table_name, new_df)
    log = []

    for col in drift["new_columns"]:
        sql_type = "TEXT"  # safe default for a newly appearing column
        conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" {sql_type};')
        log.append(f"New column '{col}' detected in upload — added to table '{table_name}'.")

    load_dataframe(conn, new_df, table_name, if_exists="append")
    log.append(f"Appended {len(new_df)} new rows to '{table_name}'.")

    return {"drift": drift, "log": log}


if __name__ == "__main__":
    from schema_inference import profile_dataset

    df1 = pd.DataFrame({
        "order_id": [1, 2, 3],
        "amount": [120.5, 89.0, 45.0],
    })
    conn = sqlite3.connect(":memory:")
    schema = profile_dataset(df1, "orders")
    print(create_table_from_schema(conn, schema))
    load_dataframe(conn, df1, "orders", if_exists="append")

    # Simulate a later upload with a new column (schema drift)
    df2 = pd.DataFrame({
        "order_id": [4, 5],
        "amount": [60.0, 30.0],
        "region": ["West", "East"],   # new column
    })
    result = append_new_data(conn, "orders", df2)
    print(result["log"])

    print(pd.read_sql("SELECT * FROM orders", conn))
