"""Accès aux trois sources, détenu uniquement par le processus MCP.

Toutes les connexions utilisent agent_ro, une limite de temps et un rollback.
Les valeurs de recherche sont paramétrées ; les identifiants viennent du catalogue.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal

import psycopg
import pymssql

from .catalog import SENSITIVE, table_definition
from .config import Settings, SOURCES
from .journal import Journal
from .validation import validate


def serializable(value):
    if isinstance(value, Decimal):
        return str(value)  # Préserve les centimes ; l'évaluation utilise Decimal.
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return "[binaire omis]"
    return value


class SourceService:
    def __init__(self, settings: Settings, catalog: dict, journal=None):
        self.settings, self.catalog = settings, catalog
        self.journal = journal if journal is not None else Journal(settings.journal_dsn)
        self.question = os.getenv("T2SQL_QUESTION", "[exploration ou vérification]")

    def _query(self, source: str, sql: str, params: tuple = (), row_limit: int | None = None) -> dict:
        """Exécute une lecture interne ou validée et journalise même les erreurs."""
        if source not in SOURCES:
            raise ValueError("Source inconnue")
        if not self.settings.source_password:
            raise ValueError("T2SQL_SOURCE_PASSWORD/AGENT_RO_PASSWORD manquant")
        limit = row_limit or self.settings.max_rows
        with self.journal.access(self.question, source, sql) as observation:
            con = None
            try:
                if source == "erp":
                    con = pymssql.connect(server="127.0.0.1", port=self.settings.erp_port, user="agent_ro", password=self.settings.source_password, database="GESPRO", timeout=self.settings.timeout_s, login_timeout=5, autocommit=False, charset="UTF-8")
                    cur = con.cursor()
                else:
                    con = psycopg.connect(host="127.0.0.1", port=getattr(self.settings, SOURCES[source]["port_setting"]), user="agent_ro", password=self.settings.source_password, dbname=SOURCES[source]["database"], connect_timeout=5, options=f"-c default_transaction_read_only=on -c statement_timeout={self.settings.timeout_s * 1000}")
                    cur = con.cursor()
                cur.execute(sql, params)
                columns = [c[0] for c in cur.description] if cur.description else []
                records = cur.fetchmany(limit + 1)
                truncated = len(records) > limit
                observation.update(row_count=min(len(records), limit), truncated=truncated)
                return {"source": source, "columns": columns, "rows": [[serializable(v) for v in row] for row in records[:limit]], "truncated": truncated}
            finally:
                if con is not None:
                    try:
                        con.rollback()
                    finally:
                        con.close()

    def list_sources(self) -> list[dict]:
        return [{"source": k, "database": v["database"], "dialect": v["dialect"], "table_count": len(self.catalog["sources"][k]["tables"]), "user": "agent_ro", "snapshot": "2026-05-31"} for k, v in SOURCES.items()]

    def list_tables(self, source: str) -> list[dict]:
        if source not in SOURCES:
            raise ValueError("Source inconnue")
        result = []
        for table in self.catalog["sources"][source]["tables"].values():
            name = table["name"]
            count = self._query(source, f'SELECT COUNT(*) AS row_count FROM "{name}"' if source != "erp" else f"SELECT COUNT(*) AS row_count FROM [dbo].[{name}]")
            result.append({"table": name, "row_count": count["rows"][0][0], "description": table["description"]})
        return result

    def get_table_card(self, source: str, table: str) -> dict:
        definition = table_definition(self.catalog, source, table)
        card = json.loads(json.dumps(definition))
        card["source"] = source
        card["row_count"] = self._query(source, f'SELECT COUNT(*) FROM "{definition["name"]}"' if source != "erp" else f'SELECT COUNT(*) FROM [dbo].[{definition["name"]}]')["rows"][0][0]
        card["example_values"] = {}
        for name, column in definition["columns"].items():
            if name.casefold() in SENSITIVE or source == "paie":
                continue
            # Seulement les codes ; pas de lignes arbitraires ni de noms personnels.
            if any(word in name.casefold() for word in ("code", "type", "statut", "status", "fam_gamme")):
                card["example_values"][name] = self.find_values(source, definition["name"], name, "", limit=8)["values"]
        from .ontology import relevant_terms
        card["ontology_terms"] = relevant_terms(table) if os.getenv("T2SQL_USE_ONTOLOGY", "1") == "1" else []
        return card

    def find_values(self, source: str, table: str, column: str, value: str, limit: int = 10) -> dict:
        definition = table_definition(self.catalog, source, table)
        if column not in definition["columns"]:
            raise ValueError("Colonne inconnue")
        if column.casefold() in SENSITIVE or source == "paie":
            raise ValueError("Recherche de valeurs individuelles de paie non autorisée")
        if len(value) > 120:
            raise ValueError("Valeur trop longue")
        limit = min(20, max(1, limit))
        if source == "erp":
            query = f"SELECT DISTINCT TOP {limit} [{column}] AS value FROM [dbo].[{definition['name']}] WHERE CAST([{column}] AS NVARCHAR(4000)) LIKE %s ORDER BY [{column}]"
        else:
            query = f'SELECT DISTINCT "{column}" AS value FROM "{definition["name"]}" WHERE CAST("{column}" AS TEXT) ILIKE %s ORDER BY "{column}" LIMIT {limit}'
        data = self._query(source, query, ("%" + value + "%",), row_limit=limit)
        return {"values": [r[0] for r in data["rows"]], "truncated": data["truncated"]}

    def validate_sql(self, source: str, sql: str) -> dict:
        return validate(source, sql, self.catalog, self.settings.max_rows)

    def execute_sql(self, source: str, sql: str) -> dict:
        checked = self.validate_sql(source, sql)
        if not checked["valid"]:
            self.journal.record(question=self.question, source=source, sql=sql[:24000], stage="validation_rejected", error=checked["error"])
            return checked
        data = self._query(source, checked["sql"], row_limit=checked["limit"])
        # Le LIMIT ajouté peut masquer des lignes supplémentaires : signal conservateur
        # lorsque le plafond est atteint, même si le jeu source compte exactement N lignes.
        data["truncated"] = data["truncated"] or len(data["rows"]) >= checked["limit"]
        return {"valid": True, "sql": checked["sql"], **data}
