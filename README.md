# AutoAnalyst

A schema-agnostic AI data platform that auto-infers database schema from raw datasets, handles incremental data appends, and lets users query & generate business reports via natural language — no manual SQL or ETL required.

Built for small businesses and teams without a dedicated data engineer.

## Status: Phase 1 + Append Engine (in progress)

- [x] Auto schema inference (column types, primary key detection, data quality warnings)
- [x] Dynamic SQL table creation from inferred schema
- [x] Append engine with schema drift detection (auto-adds new columns)
- [x] FastAPI backend with upload/append/preview endpoints
- [x] Natural language → SQL query layer (with safety validation — read-only, single-statement queries only)
- [ ] Insight/report generator
- [ ] Transparency log UI
- [ ] Iteration memory (conversational follow-ups)
- [ ] Streamlit frontend

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
[Coming next] Insight/report generation from results
```

## Tech Stack

- **Backend:** Python, FastAPI
- **Database:** SQLite (dev) — designed to be swappable for Postgres
- **Schema inference:** Pandas + custom type/relationship detection
- **AI layer (upcoming):** Claude/OpenAI API for NL→SQL and insight generation

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

## Try it out

1. Open `/docs` in your browser
2. Use `POST /upload` with `table_name=sales_orders` and upload `sample_data/sales_orders.csv`
3. Check the response — it shows the inferred schema, detected primary key, and the exact SQL used to build the table
4. Use `POST /append` with the same `table_name` and upload `sample_data/sales_orders_new_batch.csv` — notice it auto-detects the new `payment_method` column and adds it without breaking anything
5. Use `GET /tables/sales_orders` to see the combined data
6. Use `POST /query` with `table_name=sales_orders` and `question=What's the total amount by region?` — Claude generates the SQL, it runs, and you get results back with the exact query used

## Project structure

```
autoanalyst/
├── app/
│   ├── main.py                 # FastAPI app & endpoints
│   ├── schema_inference.py     # Auto-profiling & type inference
│   ├── db_builder.py           # Dynamic table creation & append engine
│   └── query_engine.py         # Natural language → SQL → results
├── sample_data/
│   ├── sales_orders.csv
│   └── sales_orders_new_batch.csv
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Why this project

Enterprise tools like Fivetran, Databricks, and Matillion already automate schema inference and ETL — but they assume a data team exists to configure and monitor them, and they're built for companies that can already afford that infrastructure. AutoAnalyst explores the same core architecture at a scale and simplicity accessible to small businesses and non-technical users: drop in a file, get a working database and a working knowledge of it, with every decision explained in plain language.
