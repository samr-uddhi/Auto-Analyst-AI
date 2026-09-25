# AutoAnalyst

A schema-agnostic AI data platform that auto-infers database schema from raw datasets, handles incremental data appends, and lets users query & generate business reports via natural language — no manual SQL or ETL required.

Built for small businesses and teams without a dedicated data engineer.

## Status: All 8 phases complete ✅

- [x] Auto schema inference (column types, primary key detection, data quality warnings)
- [x] Dynamic SQL table creation from inferred schema
- [x] Append engine with schema drift detection (auto-adds new columns)
- [x] FastAPI backend with upload/append/preview endpoints
- [x] Natural language → SQL query layer (with safety validation — read-only, single-statement queries only)
- [x] Insight/report generator (plain-English business summary of results)
- [x] Transparency log (every schema, append, query, and insight decision recorded in plain English)
- [x] Iteration memory (follow-up questions build on the previous query)
- [x] Streamlit frontend (upload, chat, schema view, and transparency log in one screen)
- [x] Multi-domain testing (sales, HR, inventory) — proven schema-agnostic, see results below

## Architecture

```
Upload dataset (CSV/Excel)
        ↓
Auto-profile & schema inference (schema_inference.py)
        ↓
Dynamic SQL table creation (db_builder.py)
        ↓
Append Engine — new uploads detect schema drift, auto-add columns
        ↓
Natural language query layer (query_engine.py)
   → Claude generates SQL from the question + schema
   → SQL is validated (read-only, single statement, no destructive keywords)
   → query runs, results returned
        ↓
Insight generator (insight_generator.py)
   → results are summarized into a plain-English business takeaway
   → e.g. "North region leads with $270 in sales, more than 3x East's total."
        ↓
Transparency log (transparency_log.py)
   → every schema choice, append, query, and insight is recorded per table
   → GET /log/{table_name} shows the full plain-English decision history
        ↓
Iteration memory (conversation_memory.py)
   → recent question/SQL pairs are remembered per table
   → a follow-up like "now break that down by month" builds on the
     previous query instead of starting from scratch
        ↓
Streamlit UI (streamlit_app.py)
   → upload/append, chat-style Q&A, schema view, and the transparency
     log all in one screen — the demoable front end
        ↓
Multi-domain test (test_multi_domain.py)
   → the entire pipeline run against sales, HR, and inventory data —
     confirms it's genuinely schema-agnostic, not hardcoded to one shape
```

## Tech Stack

- **Backend:** Python, FastAPI
- **Frontend:** Streamlit + Plotly (chat-style Q&A, dashboard, transparency log)
- **Database:** SQLite (dev) — designed to be swappable for Postgres
- **Schema inference:** Pandas + custom type/relationship detection
- **AI layer:** Claude (Anthropic API) for NL→SQL and insight generation

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/samr-uddhi/Auto-Analyst-AI.git
cd Auto-Analyst-AI

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your Anthropic API key
cp .env.example .env
# then open .env and paste your key in place of "your-api-key-here"

# 5. Run the API
cd app
uvicorn main:app --reload
```

Visit **http://127.0.0.1:8000/docs** for the interactive API (Swagger UI).

**Or run the full UI instead of the raw API:**
```bash
streamlit run app/streamlit_app.py
```
This opens the complete experience in your browser — upload a file, chat with your data, see the dashboard, schema, and transparency log all in one place. This is the version to screenshot/record for your README or resume.

## Try it out

1. Open `/docs` in your browser
2. Use `POST /upload` with `table_name=sales_orders` and upload `sample_data/sales_orders.csv`
3. Check the response — it shows the inferred schema, detected primary key, and the exact SQL used to build the table
4. Use `POST /append` with the same `table_name` and upload `sample_data/sales_orders_new_batch.csv` — notice it auto-detects the new `payment_method` column and adds it without breaking anything
5. Use `GET /tables/sales_orders` to see the combined data
6. Use `POST /query` with `table_name=sales_orders` and `question=What's the total amount by region?` — Claude generates the SQL, it runs, and you get back the results **plus a plain-English insight summarizing what they mean**
7. Use `GET /log/sales_orders` to see the full transparency log — every schema decision, append, query, and insight generated so far, in plain English with timestamps
8. Ask a follow-up in `POST /query` without repeating context — e.g. after "total amount by region", ask `question=now just show the top one` — it resolves against the previous query automatically. Use `POST /reset-conversation/sales_orders` to start a fresh conversation thread

## Project structure

```
autoanalyst/
├── app/
│   ├── main.py                 # FastAPI app & endpoints
│   ├── schema_inference.py     # Auto-profiling & type inference
│   ├── db_builder.py           # Dynamic table creation & append engine
│   ├── query_engine.py         # Natural language → SQL → results
│   ├── insight_generator.py    # Results → plain-English business insight
│   ├── transparency_log.py     # Records every AI decision in plain English
│   ├── conversation_memory.py  # Follow-up question context per table
│   ├── streamlit_app.py        # Full UI: upload, chat, dashboard, transparency log
│   └── test_multi_domain.py    # Proves the pipeline generalizes across 3 domains
├── sample_data/
│   ├── sales_orders.csv
│   ├── sales_orders_new_batch.csv
│   ├── hr_employees.csv
│   ├── hr_employees_new_batch.csv
│   ├── inventory_stock.csv
│   └── inventory_stock_new_batch.csv
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Proof of generalizability

`app/test_multi_domain.py` runs the full pipeline — schema inference, table creation, and append with schema drift — against three unrelated datasets with no dataset-specific code. Actual output:

| Domain | Columns auto-detected | Primary key found | New column auto-added on append | Final rows |
|---|---|---|---|---|
| Sales orders | 5 | `order_id` | `payment_method` | 7 |
| HR employees | 7 | `employee_id` | `remote_status` | 9 |
| Inventory stock | 6 | `sku` | `restock_date` | 9 |

Each domain got a different, correctly-detected primary key and a different auto-added column on append — proof the system reasons about whatever schema it's given rather than assuming a fixed shape. Run it yourself:
```bash
cd app
python3 test_multi_domain.py
```
(Set `ANTHROPIC_API_KEY` first to also see the NL query + insight layer tested against all three domains.)

## Why this project

Enterprise tools like Fivetran, Databricks, and Matillion already automate schema inference and ETL — but they assume a data team exists to configure and monitor them, and they're built for companies that can already afford that infrastructure. AutoAnalyst explores the same core architecture at a scale and simplicity accessible to small businesses and non-technical users: drop in a file, get a working database and a working knowledge of it, with every decision explained in plain language.
