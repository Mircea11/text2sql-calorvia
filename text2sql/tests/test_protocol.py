"""Contrats MCP, LangGraph, rapprochement Decimal et client officiel OpenAI."""
import asyncio
import os
import sys

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

from text2sql.agent import REQUIRED_TOOLS, make_graph, normalize_key, reconcile
from text2sql.api import create_app
from text2sql.config import ROOT, Settings


def test_real_mcp_stdio_discovery_and_validation():
    async def run():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "text2sql.mcp_server"], cwd=str(ROOT), env={**os.environ, "T2SQL_JOURNAL_DSN": "postgresql://test@127.0.0.1/test"})
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert {t.name for t in (await session.list_tools()).tools} == REQUIRED_TOOLS
                response = await session.call_tool("validate_sql", {"source": "compta", "sql": "SELECT 1; DELETE FROM budget"})
                assert '"valid": false' in response.content[0].text
    asyncio.run(run())


def test_graph_actually_calls_and_consumes_a_tool():
    class ScriptedModel:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            if any(isinstance(m, ToolMessage) for m in messages):
                return AIMessage(content="Réponse provenant de la sortie vérifiée de l'outil.")
            return AIMessage(content="", tool_calls=[{"id": "call1", "name": "read_value", "args": {}}])
    calls = []
    def read_value() -> dict:
        """Lecture simulée, sans connexion aux sources."""
        calls.append(True)
        return {"value": "123.45"}
    result = asyncio.run(make_graph(ScriptedModel(), [StructuredTool.from_function(read_value)]).ainvoke({"messages": [HumanMessage("Une question de test")]}))
    assert calls == [True]
    assert any(isinstance(m, ToolMessage) for m in result["messages"])


def test_decimal_reconciliation_and_normalization():
    executions = {"e1": {"columns": ["vat", "amount"], "rows": [["BE 0123.456.789", "0.30"]]}, "e2": {"columns": ["tva", "total"], "rows": [["BE0123456789", "0.10"]]}}
    result = reconcile(executions, "e1", "e2", "amount", "total", left_key="vat", right_key="tva", normalization="vat")
    assert result["rows"][0]["result"] == "0.20"
    assert normalize_key("M10300", "employee") == normalize_key("10300", "employee")
    executions["e2"]["rows"].append(["BE0123456789", "0.20"])
    with pytest.raises(ValueError): reconcile(executions, "e1", "e2", "amount", "total", left_key="vat", right_key="tva", normalization="vat")


def test_refuses_truncated_reconciliation():
    data = {"columns": ["a"], "rows": [["1"]], "truncated": True}
    with pytest.raises(ValueError): reconcile({"a": data, "b": data}, "a", "b", "a", "a")


def test_official_openai_client_nonstream_and_sse():
    async def responder(question, **kwargs):
        assert question == "Bonjour"
        return {"answer": "Réponse de contrat API, sans modèle."}
    async def run():
        app = create_app(responder, Settings(api_key="test-only"))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            assert (await http.get("/v1/models")).status_code == 401
            client = AsyncOpenAI(base_url="http://test/v1", api_key="test-only", http_client=http)
            models = await client.models.list()
            assert models.data[0].id == "calorvia-agent"
            response = await client.chat.completions.create(model="calorvia-agent", messages=[{"role": "user", "content": "Bonjour"}])
            assert "contrat API" in response.choices[0].message.content
            stream = await client.chat.completions.create(model="calorvia-agent", messages=[{"role": "user", "content": "Bonjour"}], stream=True)
            text = "".join([chunk.choices[0].delta.content or "" async for chunk in stream])
            assert "contrat API" in text
            invalid = await http.post("/v1/chat/completions", headers={"Authorization": "Bearer test-only"}, json={"model": "wrong", "messages": [{"role": "user", "content": "Bonjour"}]})
            assert invalid.status_code == 404
    asyncio.run(run())
