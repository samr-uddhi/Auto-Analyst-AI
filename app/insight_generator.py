"""
insight_generator.py
---------------------
Phase 4: turns raw SQL query results into a plain-English business
insight, instead of leaving the user to interpret a table of numbers.

This is what separates "a tool that runs SQL" from "a tool that acts
like an analyst" — the whole point of AutoAnalyst.
"""

from anthropic import Anthropic


def _format_results_for_prompt(results: list[dict], max_rows: int = 30) -> str:
    """Converts result rows into a compact text table for the prompt.
    Caps rows sent to the model to keep prompts small and cheap."""
    if not results:
        return "(no rows returned)"

    columns = list(results[0].keys())
    header = " | ".join(columns)
    rows = [
        " | ".join(str(row.get(c, "")) for c in columns)
        for row in results[:max_rows]
    ]
    table = "\n".join([header, "-" * len(header)] + rows)

    if len(results) > max_rows:
        table += f"\n... ({len(results) - max_rows} more rows not shown)"
    return table


def generate_insight(question: str, sql: str, results: list[dict],
                      client: Anthropic | None = None) -> str:
    """Asks Claude to summarize query results as a short, plain-English
    business insight — not a restatement of the numbers, but what they
    mean and why they might matter."""
    client = client or Anthropic()

    if not results:
        return "No matching data was found for this question."

    results_table = _format_results_for_prompt(results)

    system_prompt = (
        "You are a business data analyst. Given a question, the SQL query "
        "used to answer it, and the resulting data, write a short summary "
        "(2-4 sentences) in plain English for a non-technical business "
        "audience. Highlight the key takeaway, not just the raw numbers. "
        "Do not mention SQL or the query itself in your answer."
    )

    user_prompt = (
        f"Question: {question}\n\n"
        f"SQL used: {sql}\n\n"
        f"Results:\n{results_table}\n\n"
        "Summarize this for a business audience."
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()


if __name__ == "__main__":
    # Offline test of the formatting logic (no API call)
    sample_results = [
        {"region": "North", "total_amount": 270.5},
        {"region": "South", "total_amount": 164.5},
        {"region": "East", "total_amount": 0.0},
        {"region": "West", "total_amount": 45.0},
    ]
    print(_format_results_for_prompt(sample_results))
    print()
    print(_format_results_for_prompt([]))
