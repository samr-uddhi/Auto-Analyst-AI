"""
transparency_log.py
--------------------
Phase 5: Transparency Log.

Every decision AutoAnalyst makes on a company's behalf — why a column
was typed a certain way, why a column was picked as primary key, why a
new column got added during an append, what SQL was generated for a
question — gets recorded here in plain English, per table.

This is the project's core differentiator versus enterprise AI-ETL
tools: those show technical pipeline logs; AutoAnalyst explains itself
to a non-technical user.
"""

from datetime import datetime, timezone


# In-memory store: { table_name: [ {timestamp, category, message}, ... ] }
# In a production version this would be a database table instead.
_LOGS: dict[str, list[dict]] = {}

VALID_CATEGORIES = {"schema", "append", "query", "insight", "warning"}


def log_event(table_name: str, category: str, message: str) -> None:
    """Records one plain-English log entry for a table."""
    if category not in VALID_CATEGORIES:
        category = "warning"

    _LOGS.setdefault(table_name, []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "message": message,
    })


def log_many(table_name: str, category: str, messages: list[str]) -> None:
    """Convenience for logging a batch of messages under the same category
    (e.g. all the warnings from a single schema inference pass)."""
    for msg in messages:
        log_event(table_name, category, msg)


def get_log(table_name: str) -> list[dict]:
    """Returns the full chronological log for a table, oldest first."""
    return _LOGS.get(table_name, [])


def get_recent(table_name: str, limit: int = 10) -> list[dict]:
    """Returns the most recent `limit` entries, newest first — useful for
    a compact 'what just happened' view."""
    return list(reversed(_LOGS.get(table_name, [])))[:limit]


def clear_log(table_name: str) -> None:
    _LOGS.pop(table_name, None)


if __name__ == "__main__":
    log_event("orders", "schema", "Detected 'order_id' as the primary key.")
    log_many("orders", "warning", [
        "Column 'amount' is 40.0% empty — consider whether it's needed.",
    ])
    log_event("orders", "append", "New column 'payment_method' added — 2 rows appended.")
    log_event("orders", "query", 'Question: "total by region" -> SELECT region, SUM(amount)...')

    for entry in get_log("orders"):
        print(f"[{entry['category']}] {entry['message']}")
