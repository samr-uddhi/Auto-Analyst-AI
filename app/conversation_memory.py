"""
conversation_memory.py
------------------------
Phase 6: Iteration memory.

Keeps a short history of question -> SQL turns per table, so a
follow-up prompt like "now break that down by month" can be resolved
in the context of the previous query, instead of the user having to
repeat the whole question from scratch.

This is what turns the query layer from "one-shot NL-to-SQL" into an
actual conversational analyst.
"""

from datetime import datetime, timezone

# In-memory store: { table_name: [ {question, sql, timestamp}, ... ] }
# Kept short deliberately — only recent turns matter for follow-up context.
_HISTORY: dict[str, list[dict]] = {}

MAX_TURNS_KEPT = 10       # don't let history grow unbounded
MAX_TURNS_IN_PROMPT = 4   # how many recent turns get sent to the model


def add_turn(table_name: str, question: str, sql: str) -> None:
    turns = _HISTORY.setdefault(table_name, [])
    turns.append({
        "question": question,
        "sql": sql,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Trim oldest turns beyond the cap
    if len(turns) > MAX_TURNS_KEPT:
        _HISTORY[table_name] = turns[-MAX_TURNS_KEPT:]


def get_recent_turns(table_name: str, limit: int = MAX_TURNS_IN_PROMPT) -> list[dict]:
    """Returns the most recent turns, oldest-first, ready to feed into a
    prompt as conversational context."""
    return _HISTORY.get(table_name, [])[-limit:]


def format_history_for_prompt(table_name: str, limit: int = MAX_TURNS_IN_PROMPT) -> str:
    """Turns recent history into compact text the LLM can use to resolve
    references like 'that', 'those results', 'now also show...'."""
    turns = get_recent_turns(table_name, limit)
    if not turns:
        return ""

    lines = ["Recent conversation on this table (most recent last):"]
    for i, turn in enumerate(turns, 1):
        lines.append(f'{i}. Question: "{turn["question"]}"\n   SQL: {turn["sql"]}')
    return "\n".join(lines)


def clear_history(table_name: str) -> None:
    _HISTORY.pop(table_name, None)


if __name__ == "__main__":
    add_turn("orders", "total sales by region", 'SELECT region, SUM(amount) FROM "orders" GROUP BY region')
    add_turn("orders", "now just show the top one", 'SELECT region, SUM(amount) FROM "orders" GROUP BY region ORDER BY SUM(amount) DESC LIMIT 1')

    print(format_history_for_prompt("orders"))
