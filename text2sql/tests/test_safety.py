"""Contrats de sécurité, indépendants d'un LLM et des services de la machine."""

import ast
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from text2sql.catalog import load_catalog
from text2sql.config import Settings, local_url
from text2sql.sources import SourceService
from text2sql.validation import validate


@pytest.mark.parametrize(
    "source,sql",
    [
        ("erp", "SELECT COUNT(*) FROM dbo.VTE_FACT"),
        (
            "erp",
            "SELECT SUM(CASE WHEN FAC_TYPE='A' THEN -FAC_MT_HT ELSE FAC_MT_HT END) FROM VTE_FACT WHERE FAC_DT>='2026-03-01' AND FAC_DT<'2026-04-01'",
        ),
        (
            "compta",
            "SELECT e.code_periode,SUM(l.credit-l.debit) AS net FROM ecriture e JOIN ligne_ecriture l ON e.id_ecriture=l.id_ecriture GROUP BY e.code_periode",
        ),
        (
            "compta",
            "WITH totals AS (SELECT numero_compte,SUM(montant) AS total FROM budget GROUP BY numero_compte) SELECT * FROM totals",
        ),
        ("paie", "SELECT COUNT(DISTINCT employee_id) FROM contracts"),
        (
            "paie",
            "SELECT r.period_month,SUM(p.gross_amount) FROM payslips p JOIN payroll_runs r ON p.run_id=r.run_id GROUP BY r.period_month",
        ),
        (
            "paie",
            "SELECT COUNT(DISTINCT p.employee_id),SUM(p.gross_amount) FROM payslips p",
        ),
    ],
)
def test_valid_queries(source, sql):
    result = validate(source, sql, load_catalog())
    assert result["valid"], result


@pytest.mark.parametrize(
    "source,sql",
    [
        ("compta", "DELETE FROM budget"),
        ("compta", "SELECT 1; DELETE FROM budget"),
        (
            "compta",
            "WITH removed AS (DELETE FROM budget RETURNING *) SELECT * FROM removed",
        ),
        ("erp", "SELECT * INTO copied FROM VTE_FACT"),
        ("erp", "EXEC sp_executesql N'DELETE FROM PAR_CODE'"),
        ("compta", "SELECT pg_read_file('/etc/passwd')"),
        ("compta", "SELECT set_config('default_transaction_read_only','off',false)"),
        ("compta", "SELECT pg_sleep(60)"),
        ("compta", "SELECT * FROM pg_catalog.pg_authid"),
        ("compta", "SELECT * FROM unknown_table"),
        ("compta", "SELECT unknown_column FROM budget"),
        ("compta", "SELECT iban FROM tiers"),
        ("compta", "SELECT * FROM compte_bancaire"),
        ("erp", "SELECT * FROM compta.dbo.budget"),
        ("erp", "SELECT * FROM OPENROWSET('provider','connection','query')"),
        ("paie", "SELECT * FROM employees"),
        ("paie", "SELECT national_number AS harmless FROM employees"),
        ("paie", "SELECT MAX(iban) FROM employees"),
        ("paie", "SELECT gross_amount FROM payslips"),
        (
            "paie",
            "SELECT employee_id,SUM(gross_amount) FROM payslips GROUP BY employee_id",
        ),
        ("paie", "SELECT SUM(gross_amount) FROM payslips WHERE employee_id='M10001'"),
        (
            "paie",
            "SELECT SUM(CASE WHEN employee_id='M10001' THEN gross_amount ELSE 0 END) FROM payslips",
        ),
        (
            "paie",
            "SELECT COUNT(CASE WHEN employee_id='M10001' AND gross_amount>4000 THEN 1 END) FROM payslips",
        ),
        (
            "paie",
            "SELECT p.gross_amount,COUNT(*) FROM payslips p GROUP BY p.gross_amount",
        ),
        ("compta", "SELECT * FROM budget FOR UPDATE"),
        ("compta", "SELECT * FROM budget LIMIT -1"),
    ],
)
def test_rejects_unsafe_queries(source, sql):
    result = validate(source, sql, load_catalog())
    assert not result["valid"], result


@pytest.mark.parametrize(
    "source,sql,expected",
    [
        ("erp", "SELECT TOP 99999 FAC_NUM FROM VTE_FACT", 200),
        ("compta", "SELECT montant FROM budget LIMIT 5", 5),
        ("compta", "SELECT montant FROM budget", 200),
    ],
)
def test_row_cap(source, sql, expected):
    result = validate(source, sql, load_catalog())
    assert result["valid"] and result["limit"] == expected


def test_execution_revalidates_before_database_access():
    class Journal:
        def record(self, **kwargs):
            pass

    service = SourceService(Settings(), load_catalog(), Journal())
    service._query = lambda *a, **k: pytest.fail(
        "Une requête interdite a atteint le pilote"
    )
    assert not service.execute_sql("compta", "DELETE FROM budget")["valid"]


def test_local_endpoints_only():
    for url in [
        "https://api.openai.com/v1",
        "https://integrate.api.nvidia.com/v1",
        "http://localhost@evil.example/v1",
        "http://127.0.0.1/v1?secret=x",
    ]:
        with pytest.raises(ValueError):
            local_url(url)
    assert local_url("http://127.0.0.1:8000/v1/").endswith("/v1")


def test_agent_has_no_database_driver_or_gpu_loader():
    root = Path(__file__).parents[1]
    for filename in ["agent.py", "api.py", "ontology.py", "config.py"]:
        tree = ast.parse((root / filename).read_text())
        imports = [
            n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        ] + [
            v.name for n in ast.walk(tree) if isinstance(n, ast.Import) for v in n.names
        ]
        assert not any(
            (v or "").split(".")[0]
            in {"psycopg", "pymssql", "torch", "transformers", "sources"}
            for v in imports
        )

def test_postgres_literal_like_and_bound_value(monkeypatch):
    """Les SQL validés gardent leurs motifs LIKE ; find_values lie sa valeur."""
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.description = [("value",)]
    cursor.fetchmany.return_value = [(1,)]
    monkeypatch.setattr("text2sql.sources.psycopg.connect", lambda **kwargs: connection)
    journal = MagicMock()
    journal.access.side_effect = lambda *args: nullcontext({})
    service = SourceService(Settings(source_password="test"), load_catalog(), journal)

    result = service.execute_sql("compta", "SELECT COUNT(*) FROM ecriture WHERE code_periode LIKE '2025-%'")
    assert result["valid"] and "2025-%" in result["sql"]
    cursor.execute.assert_called_once_with(result["sql"])

    service.find_values("compta", "ecriture", "code_periode", "2025-")
    bound_sql, values = cursor.execute.call_args.args
    assert "ILIKE %s" in bound_sql and values == ("%2025-%",)
