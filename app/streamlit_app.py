"""
streamlit_app.py
------------------
Phase 7: the demoable front end.

Ties every earlier phase together into one screen:
  - upload a dataset -> auto schema inference + table creation
  - append a new file -> auto schema drift handling
  - ask questions in a chat interface -> NL -> SQL -> results -> insight,
    with follow-up questions resolved via conversation memory
  - see the transparency log -> every decision explained in plain English

Run with:  streamlit run streamlit_app.py
"""

import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.express as px

from schema_inference import profile_dataset
from db_builder import create_table_from_schema, load_dataframe, append_new_data
from query_engine import answer_question, UnsafeQueryError
from transparency_log import log_event, log_many, get_log
from conversation_memory import add_turn, format_history_for_prompt, clear_history


st.set_page_config(page_title="AutoAnalyst", page_icon="📊", layout="wide")


# ---- Session state setup ----
# Each Streamlit session gets its own SQLite file so demos don't collide.
if "db_path" not in st.session_state:
    tmp_dir = tempfile.mkdtemp()
    st.session_state.db_path = str(Path(tmp_dir) / "autoanalyst_session.db")

if "schema_registry" not in st.session_state:
    st.session_state.schema_registry = {}

if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}   # { table_name: [ {role, content}, ... ] }


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(st.session_state.db_path)


def read_uploaded_file(uploaded_file) -> pd.DataFrame:
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    return pd.read_excel(uploaded_file)


# ---- Sidebar: dataset upload / append ----
with st.sidebar:
    st.title("📊 AutoAnalyst")
    st.caption("Upload data → ask questions in plain English.")

    st.subheader("1. Upload a dataset")
    table_name_input = st.text_input("Table name", placeholder="e.g. sales_orders")
    uploaded_file = st.file_uploader("CSV or Excel file", type=["csv", "xlsx", "xls"])

    existing_tables = list(st.session_state.schema_registry.keys())
    is_existing = table_name_input in existing_tables

    action_label = "➕ Append to existing table" if is_existing else "🆕 Create new table"

    if st.button(action_label, disabled=not (table_name_input and uploaded_file)):
        df = read_uploaded_file(uploaded_file)
        conn = get_conn()

        if is_existing:
            result = append_new_data(conn, table_name_input, df)
            log_many(table_name_input, "append", result["log"])
            st.success(f"Appended {len(df)} rows to '{table_name_input}'.")
            for msg in result["log"]:
                st.info(msg)
        else:
            schema = profile_dataset(df, table_name_input)
            create_table_from_schema(conn, schema)
            load_dataframe(conn, df, table_name_input, if_exists="append")
            st.session_state.schema_registry[table_name_input] = schema
            st.session_state.chat_history[table_name_input] = []
            log_event(table_name_input, "schema", f"Table '{table_name_input}' created from {len(df)} uploaded rows.")
            log_many(table_name_input, "warning", schema["warnings"])
            st.success(f"Created table '{table_name_input}' with {len(df)} rows.")
            for warning in schema["warnings"]:
                st.info(warning)

        conn.close()

    st.divider()
    if existing_tables:
        st.subheader("2. Select a table to explore")
        active_table = st.radio("Tables", existing_tables, label_visibility="collapsed")
    else:
        active_table = None
        st.caption("No tables yet — upload a dataset to get started.")


# ---- Main area ----
if not active_table:
    st.title("Welcome to AutoAnalyst")
    st.write(
        "Upload any CSV or Excel file in the sidebar. AutoAnalyst will automatically "
        "infer the schema, build a database, and let you ask questions about it in "
        "plain English — no SQL required."
    )
else:
    st.title(f"📁 {active_table}")
    tab_chat, tab_data, tab_log, tab_schema = st.tabs(
        ["💬 Ask Questions", "📋 Data Preview", "🔍 Transparency Log", "🧬 Schema"]
    )

    # --- Chat tab ---
    with tab_chat:
        col1, col2 = st.columns([5, 1])
        with col2:
            if st.button("🔄 Reset conversation"):
                clear_history(active_table)
                st.session_state.chat_history[active_table] = []
                st.rerun()

        for msg in st.session_state.chat_history.get(active_table, []):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("dataframe") is not None and not msg["dataframe"].empty:
                    st.dataframe(msg["dataframe"], use_container_width=True)
                    numeric_cols = msg["dataframe"].select_dtypes(include="number").columns
                    if len(msg["dataframe"].columns) >= 2 and len(numeric_cols) >= 1:
                        try:
                            label_col = [c for c in msg["dataframe"].columns if c not in numeric_cols][0]
                            fig = px.bar(msg["dataframe"], x=label_col, y=numeric_cols[0])
                            st.plotly_chart(fig, use_container_width=True)
                        except Exception:
                            pass  # chart is a bonus, never block the answer

        question = st.chat_input(f"Ask something about {active_table}...")
        if question:
            st.session_state.chat_history.setdefault(active_table, []).append(
                {"role": "user", "content": question, "dataframe": None}
            )
            with st.chat_message("user"):
                st.markdown(question)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    schema = st.session_state.schema_registry[active_table]
                    history_context = format_history_for_prompt(active_table)
                    conn = get_conn()
                    try:
                        result = answer_question(
                            question, schema, conn, history_context=history_context
                        )
                        add_turn(active_table, question, result["sql_generated"])
                        log_event(active_table, "query", f'"{question}" -> {result["sql_generated"]}')
                        log_event(active_table, "insight", result["insight"])

                        st.markdown(result["insight"])
                        results_df = pd.DataFrame(result["results"])
                        if not results_df.empty:
                            st.dataframe(results_df, use_container_width=True)
                        with st.expander("SQL used"):
                            st.code(result["sql_generated"], language="sql")

                        st.session_state.chat_history[active_table].append({
                            "role": "assistant",
                            "content": result["insight"],
                            "dataframe": results_df,
                        })
                    except UnsafeQueryError as e:
                        error_msg = f"That question was blocked for safety: {e}"
                        st.error(error_msg)
                        log_event(active_table, "warning", f"Blocked query for '{question}' — {e}")
                        st.session_state.chat_history[active_table].append(
                            {"role": "assistant", "content": error_msg, "dataframe": None}
                        )
                    finally:
                        conn.close()

    # --- Data preview tab ---
    with tab_data:
        conn = get_conn()
        df_preview = pd.read_sql(f'SELECT * FROM "{active_table}" LIMIT 200', conn)
        conn.close()
        st.dataframe(df_preview, use_container_width=True)
        st.caption(f"Showing up to 200 rows of '{active_table}'.")

    # --- Transparency log tab ---
    with tab_log:
        log_entries = get_log(active_table)
        if not log_entries:
            st.caption("No log entries yet.")
        else:
            for entry in reversed(log_entries):
                icon = {
                    "schema": "🧬", "append": "➕", "query": "❓",
                    "insight": "💡", "warning": "⚠️",
                }.get(entry["category"], "•")
                st.markdown(f"{icon} **{entry['category'].title()}** — {entry['message']}")
                st.caption(entry["timestamp"])
                st.divider()

    # --- Schema tab ---
    with tab_schema:
        schema = st.session_state.schema_registry[active_table]
        st.write(f"**Primary key:** `{schema['primary_key'] or 'none detected — auto-increment ID used'}`")
        st.write(f"**Row count:** {schema['row_count']}")
        col_df = pd.DataFrame(schema["columns"])
        st.dataframe(col_df, use_container_width=True)
