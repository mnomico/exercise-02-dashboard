"""
ASGI entrypoint for the dashboard.

Streamlit serves an empty HTML shell and renders everything client-side over a
WebSocket, so clients that do not run JavaScript (curl, requests, crawlers) see
no content. This wraps app.py in st.App and adds a middleware that, on every
GET of the root page, fetches the node list from the API and renders it inside
<div id="root">. Browsers replace that markup as soon as the React app mounts.
"""

import asyncio
import html
import os

import requests
import streamlit as st
from starlette.middleware import Middleware

API_URL = os.environ.get("API_URL", "http://api:8080").rstrip("/")
ROOT_DIV = b'<div id="root"></div>'


def fetch_nodes() -> list[dict] | None:
    try:
        resp = requests.get(f"{API_URL}/api/nodes", timeout=3)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError):
        return None


def render_nodes(nodes: list[dict] | None) -> str:
    parts = ["<h1>Node Registry Dashboard</h1>", "<h2>Nodes</h2>"]
    if nodes is None:
        parts.append(f"<p>API unreachable at {html.escape(API_URL)}</p>")
    elif not nodes:
        parts.append("<p>No nodes registered yet.</p>")
    else:
        rows = "".join(
            "<tr>"
            + "".join(f"<td>{html.escape(str(n.get(k, '')))}</td>" for k in ("name", "host", "port", "status"))
            + "</tr>"
            for n in nodes
        )
        parts.append(
            "<table><thead><tr><th>name</th><th>host</th><th>port</th><th>status</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    return "".join(parts)


class ServerRenderedNodesMiddleware:
    """Injects the node table into the HTML of the root page."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "GET" or scope["path"] != "/":
            await self.app(scope, receive, send)
            return

        # Ask for an uncompressed body so it can be rewritten.
        scope = dict(scope)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"accept-encoding"]

        start = None
        body = bytearray()

        async def capture(message):
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
                return
            body.extend(message.get("body", b""))
            if message.get("more_body"):
                return

            headers = [(k, v) for k, v in start["headers"] if k.lower() != b"content-length"]
            content_type = dict((k.lower(), v) for k, v in headers).get(b"content-type", b"")
            payload = bytes(body)
            if b"text/html" in content_type and ROOT_DIV in payload:
                nodes = await asyncio.to_thread(fetch_nodes)
                rendered = f'<div id="root">{render_nodes(nodes)}</div>'.encode()
                payload = payload.replace(ROOT_DIV, rendered, 1)
            headers.append((b"content-length", str(len(payload)).encode()))
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": payload})

        await self.app(scope, receive, capture)


app = st.App("app.py", middleware=[Middleware(ServerRenderedNodesMiddleware)])
