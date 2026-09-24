"""
schema_inference.py
--------------------
Auto-profiles any uploaded dataset (CSV/Excel) and infers:
- column data types (mapped to SQL types)
- likely primary key
- nullability
- basic data quality flags (duplicates, high-null columns)

This is Phase 1 of AutoAnalyst: turning a raw, messy file into a
structured schema definition the system can use to build a database.
"""

import pandas as pd
import re


# ---- Type mapping: pandas dtype -> SQL type ----
def _map_dtype_to_sql(series: pd.Series) -> str:
    """Infer a SQL column type from a pandas Series, with light heuristics
    beyond pandas' own dtype (e.g. detecting dates stored as strings)."""

    # Try datetime detection on text-like columns first (covers both the
    # classic 'object' dtype and pandas' newer dedicated string dtype)
    if series.dtype == object or pd.api.types.is_string_dtype(series):
        sample = series.dropna().astype(str).head(20)
        date_like = sample.apply(_looks_like_date)
        if len(sample) > 0 and date_like.mean() > 0.8:
            return "DATETIME"

    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "DATETIME"

    # Default: text. Distinguish short categorical-like text from long text.
    max_len = series.dropna().astype(str).map(len).max() if series.notna().any() else 0
    return "VARCHAR" if (max_len or 0) <= 255 else "TEXT"


def _looks_like_date(value: str) -> bool:
    patterns = [
        r"^\d{4}-\d{2}-\d{2}",           # 2024-01-31
        r"^\d{2}/\d{2}/\d{4}",           # 31/01/2024
        r"^\d{2}-\d{2}-\d{4}",           # 31-01-2024
    ]
    return any(re.match(p, value.strip()) for p in patterns)


def _guess_primary_key(df: pd.DataFrame) -> str | None:
    """A column is a good primary-key candidate if it's unique and
    non-null across the whole dataset, and its name hints at an ID."""
    candidates = []
    for col in df.columns:
        if df[col].is_unique and df[col].notna().all():
            candidates.append(col)

    # Prefer columns whose name suggests an identifier
    for col in candidates:
        if re.search(r"(^id$|_id$|^id_|code$)", col, flags=re.IGNORECASE):
            return col

    # Otherwise return the first fully-unique column, if any
    return candidates[0] if candidates else None


def profile_dataset(df: pd.DataFrame, table_name: str) -> dict:
    """
    Returns a schema profile dict:
    {
        "table_name": str,
        "primary_key": str | None,
        "columns": [
            {"name": ..., "sql_type": ..., "nullable": bool, "null_pct": float}
        ],
        "row_count": int,
        "duplicate_rows": int,
        "warnings": [str, ...]   # plain-English notes -> transparency log
    }
    """
    warnings = []
    columns = []

    for col in df.columns:
        series = df[col]
        sql_type = _map_dtype_to_sql(series)
        null_pct = round(series.isna().mean() * 100, 1)
        nullable = null_pct > 0

        if null_pct > 30:
            warnings.append(
                f"Column '{col}' is {null_pct}% empty — consider whether it's needed."
            )

        columns.append({
            "name": col,
            "sql_type": sql_type,
            "nullable": bool(nullable),
            "null_pct": float(null_pct),
        })

    primary_key = _guess_primary_key(df)
    if primary_key:
        warnings.append(f"Detected '{primary_key}' as the primary key (unique, no missing values).")
    else:
        warnings.append("No natural primary key found — an auto-increment ID will be added.")

    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows > 0:
        warnings.append(f"Found {duplicate_rows} fully duplicate rows.")

    return {
        "table_name": table_name,
        "primary_key": primary_key,
        "columns": columns,
        "row_count": len(df),
        "duplicate_rows": duplicate_rows,
        "warnings": warnings,
    }


if __name__ == "__main__":
    # Quick manual test
    sample = pd.DataFrame({
        "order_id": [1, 2, 3, 4],
        "customer_email": ["a@x.com", "b@x.com", "c@x.com", "c@x.com"],
        "order_date": ["2024-01-01", "2024-01-03", "2024-01-05", "2024-01-05"],
        "amount": [120.5, 89.0, None, 45.0],
    })
    import json
    print(json.dumps(profile_dataset(sample, "orders"), indent=2))
