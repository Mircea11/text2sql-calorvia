"""Vrais privilèges SQL Server/PostgreSQL : exécutés seulement avec T2SQL_LIVE=1.

Les écritures de test touchent zéro ligne et la transaction est annulée. La
validation applicative est délibérément contournée pour vérifier les privilèges.
"""

import os
import psycopg
import pymssql
import pytest
from text2sql.config import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("T2SQL_LIVE") != "1",
    reason="Sources réelles non accessibles dans cet environnement",
)


@pytest.mark.parametrize(
    "source,table,column",
    [("compta", "budget", "montant"), ("paie", "contracts", "weekly_hours")],
)
def test_postgres_acl_denies_write_even_with_readonly_default_disabled(
    source, table, column
):
    s = Settings.load()
    con = psycopg.connect(
        host="127.0.0.1",
        port=getattr(s, source + "_port"),
        user="agent_ro",
        password=s.source_password,
        dbname=source,
        connect_timeout=5,
    )
    try:
        con.execute("SET TRANSACTION READ WRITE")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            con.execute(f"UPDATE {table} SET {column}={column} WHERE FALSE")
    finally:
        con.rollback()
        con.close()


def test_sqlserver_acl_denies_write():
    s = Settings.load()
    con = pymssql.connect(
        server="127.0.0.1",
        port=s.erp_port,
        user="agent_ro",
        password=s.source_password,
        database="GESPRO",
        login_timeout=5,
        timeout=10,
    )
    try:
        with pytest.raises(pymssql.DatabaseError) as rejected:
            con.cursor().execute("UPDATE dbo.PAR_CODE SET COD_VAL=COD_VAL WHERE 1=0")
        assert "229" in repr(rejected.value.args), rejected.value.args
    finally:
        con.rollback()
        con.close()


def test_payroll_national_number_unreadable_at_database_level():
    s = Settings.load()
    con = psycopg.connect(
        host="127.0.0.1",
        port=s.paie_port,
        user="agent_ro",
        password=s.source_password,
        dbname="paie",
        connect_timeout=5,
    )
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            con.execute("SELECT national_number FROM employees LIMIT 0")
    finally:
        con.rollback()
        con.close()
