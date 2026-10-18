"""Guardrail tests: what the agent can and cannot reach."""

import asyncio
import sys

import pytest

from jobagent import server, tools

FORBIDDEN = {"approve_change", "reject_change", "rollback_change", "delete_application",
             "run_sql", "execute_sql", "send_email", "list_pending"}


def test_exposed_tool_names_exclude_human_only_actions():
    assert FORBIDDEN.isdisjoint(server.EXPOSED_TOOLS)


def test_registered_mcp_tools_match_allow_list():
    registered = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert registered == set(server.EXPOSED_TOOLS)


def test_injected_note_is_returned_as_data_and_changes_nothing(database):
    rows = tools.search_applications("IGNORE ALL PREVIOUS")["applications"]
    assert len(rows) == 1  # the hostile note is stored text only
    assert tools.list_applications()["count"] == 7  # nothing was deleted


def test_mcp_stdio_roundtrip(database, monkeypatch):
    mcp = pytest.importorskip("mcp")
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "jobagent.server"], env=dict(os.environ)
        )
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            res = await s.call_tool("list_applications", {"status": "interview"})
            return names, "".join(getattr(c, "text", "") for c in res.content)

    names, text = asyncio.run(go())
    assert names == set(server.EXPOSED_TOOLS)
    assert "Kestrel Bio" in text
    assert mcp is not None
