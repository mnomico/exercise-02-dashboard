"""
Exercise 02 — Streamlit Dashboard

Streamlit frontend that consumes the Node Registry API.

- Displays a table of all registered nodes (GET /api/nodes)
- Registers a new node (POST /api/nodes)
- Soft-deletes a node by name (DELETE /api/nodes/{name})
- Shows API health status and active node count (GET /health)

The API base URL comes from the API_URL environment variable (default: http://api:8080).
"""

import os

import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://api:8080").rstrip("/")
TIMEOUT = 5

st.set_page_config(page_title="Node Registry", layout="wide")
st.title("Node Registry Dashboard")


def api(method: str, path: str, **kwargs) -> requests.Response:
    return requests.request(method, f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)


def error_detail(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("detail", resp.text))
    except ValueError:
        return resp.text


# Feedback from the previous action survives the st.rerun() below.
if "flash" in st.session_state:
    kind, msg = st.session_state.pop("flash")
    getattr(st, kind)(msg)


def flash(kind: str, msg: str) -> None:
    st.session_state["flash"] = (kind, msg)
    st.rerun()


# --- Health indicator -------------------------------------------------------
st.subheader("Health")
try:
    health = api("GET", "/health").json()
    col_status, col_db, col_count = st.columns(3)
    col_status.metric("API status", health.get("status", "unknown"))
    col_db.metric("Database", health.get("db", "unknown"))
    col_count.metric("Active nodes", health.get("nodes_count", 0))
    if health.get("status") == "ok" and health.get("db") == "connected":
        st.success("API is healthy")
    else:
        st.warning("API is degraded")
except requests.RequestException as exc:
    st.error(f"API unreachable at {API_URL}: {exc}")

# --- Node list --------------------------------------------------------------
st.subheader("Nodes")
nodes: list[dict] = []
try:
    resp = api("GET", "/api/nodes")
    resp.raise_for_status()
    nodes = resp.json()
except requests.RequestException as exc:
    st.error(f"Could not load nodes: {exc}")

if nodes:
    # st.table renders a real HTML table (st.dataframe draws on a canvas).
    st.table(
        [
            {"name": n["name"], "host": n["host"], "port": n["port"], "status": n["status"]}
            for n in nodes
        ]
    )
else:
    st.info("No nodes registered yet.")

if st.button("Refresh"):
    st.rerun()

col_register, col_delete = st.columns(2)

# --- Register form ----------------------------------------------------------
with col_register:
    st.subheader("Register node")
    with st.form("register_form", clear_on_submit=True):
        name = st.text_input("Name")
        host = st.text_input("Host")
        port = st.number_input("Port", min_value=1, max_value=65535, value=8000, step=1)
        submitted = st.form_submit_button("Register")

    if submitted:
        if not name.strip() or not host.strip():
            st.error("Name and host are required.")
        else:
            try:
                resp = api(
                    "POST",
                    "/api/nodes",
                    json={"name": name.strip(), "host": host.strip(), "port": int(port)},
                )
                if resp.status_code == 201:
                    flash("success", f"Node '{name.strip()}' registered.")
                elif resp.status_code == 409:
                    st.error(f"Node '{name.strip()}' already exists.")
                else:
                    st.error(f"Error {resp.status_code}: {error_detail(resp)}")
            except requests.RequestException as exc:
                st.error(f"API unreachable: {exc}")

# --- Delete -----------------------------------------------------------------
with col_delete:
    st.subheader("Delete node")
    active_names = [n["name"] for n in nodes if n.get("status") == "active"]
    if active_names:
        to_delete = st.selectbox("Node", active_names)
        if st.button("Delete", type="primary"):
            try:
                resp = api("DELETE", f"/api/nodes/{requests.utils.quote(to_delete, safe='')}")
                if resp.status_code == 204:
                    flash("success", f"Node '{to_delete}' deleted (marked inactive).")
                elif resp.status_code == 404:
                    st.error(f"Node '{to_delete}' not found.")
                else:
                    st.error(f"Error {resp.status_code}: {error_detail(resp)}")
            except requests.RequestException as exc:
                st.error(f"API unreachable: {exc}")
    else:
        st.info("No active nodes to delete.")
