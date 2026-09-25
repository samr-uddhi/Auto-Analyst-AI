"""
test_multi_domain.py
----------------------
Phase 8: Multi-domain testing.

Proves AutoAnalyst is schema-agnostic — not hardcoded to one dataset —
by running the full pipeline (schema inference -> table creation ->
append with schema drift -> [optional] NL query + insight) across
three unrelated business domains:

  1. Sales orders   (sample_data/sales_orders.csv)
  2. HR employees    (sample_data/hr_employees.csv)
  3. Inventory stock (sample_data/inventory_stock.csv)

The schema inference / table build / append portion runs with no
external dependencies. The NL query + insight portion additionally
runs if ANTHROPIC_API_KEY is set in the environment; otherwise those
steps are skipped with a clear note, so this script works for anyone
cloning the repo without a key.

Run with:  python3 test_multi_domain.py
"""

import os
import sqlite3
import pandas as pd

from schema_inference import profile_dataset
from db_builder import create_table_from_schema, load_dataframe, append_new_data

DOMAINS = [
    {
        "table_name": "sales_orders",
        "initial_file": "../sample_data/sales_orders.csv",
        "append_file": "../sample_data/sales_orders_new_batch.csv",
        "sample_questions": [
            "What's the total amount by region?",
            "Which customer has placed the most orders?",
        ],
    },
    {
        "table_name": "hr_employees",
        "initial_file": "../sample_data/hr_employees.csv",
        "append_file": "../sample_data/hr_employees_new_batch.csv",
        "sample_questions": [
            "What's the average salary by department?",
            "How many managers are there?",
        ],
    },
    {
        "table_name": "inventory_stock",
        "initial_file": "../sample_data/inventory_stock.csv",
        "append_file": "../sample_data/inventory_stock_new_batch.csv",
        "sample_questions": [
            "Which products are out of stock?",
            "What's the total inventory value by warehouse?",
        ],
    },
]


def run_domain_test(domain: dict, conn: sqlite3.Connection) -> dict:
    table_name = domain["table_name"]
    print(f"\n{'=' * 60}\nDOMAIN: {table_name}\n{'=' * 60}")

    # --- Step 1: schema inference + table creation ---
    df = pd.read_csv(domain["initial_file"])
    schema = profile_dataset(df, table_name)
    create_table_from_schema(conn, schema)
    load_dataframe(conn, df, table_name, if_exists="append")

    print(f"Schema inferred: {len(schema['columns'])} columns, "
          f"primary key = {schema['primary_key']!r}")
    for w in schema["warnings"]:
        print(f"  - {w}")

    # --- Step 2: append with schema drift ---
    df_new = pd.read_csv(domain["append_file"])
    append_result = append_new_data(conn, table_name, df_new)
    print(f"Append test: {len(df_new)} new rows")
    for log_line in append_result["log"]:
        print(f"  - {log_line}")

    row_count = pd.read_sql(f'SELECT COUNT(*) as n FROM "{table_name}"', conn)["n"][0]
    print(f"Final row count in '{table_name}': {row_count}")

    result = {
        "table_name": table_name,
        "columns_inferred": len(schema["columns"]),
        "primary_key": schema["primary_key"],
        "new_columns_added_on_append": append_result["drift"]["new_columns"],
        "final_row_count": int(row_count),
    }

    # --- Step 3 (optional): NL query + insight, only if an API key is set ---
    if os.environ.get("ANTHROPIC_API_KEY"):
        from query_engine import answer_question
        print("Running sample NL questions (ANTHROPIC_API_KEY detected)...")
        for question in domain["sample_questions"]:
            answer = answer_question(question, schema, conn, include_insight=True)
            print(f'  Q: "{question}"')
            print(f'  SQL: {answer["sql_generated"]}')
            print(f'  Insight: {answer["insight"]}\n')
    else:
        print("Skipping NL query tests — set ANTHROPIC_API_KEY to run them.")

    return result


def main():
    conn = sqlite3.connect(":memory:")
    summary = [run_domain_test(domain, conn) for domain in DOMAINS]
    conn.close()

    print(f"\n{'=' * 60}\nSUMMARY — generalizability across {len(DOMAINS)} domains\n{'=' * 60}")
    for r in summary:
        print(f"- {r['table_name']}: {r['columns_inferred']} columns auto-detected, "
              f"PK={r['primary_key']!r}, "
              f"append added columns={r['new_columns_added_on_append']}, "
              f"final rows={r['final_row_count']}")

    all_passed = all(r["final_row_count"] > 0 for r in summary)
    print(f"\nAll domains processed successfully: {all_passed}")


if __name__ == "__main__":
    main()
