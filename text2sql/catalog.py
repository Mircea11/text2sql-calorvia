"""Catalogue sans données personnelles, extrait des DDL officiels ou relu en JSON.

Le DDL fournit les types, clés et commentaires. Les outils MCP ajoutent les
comptages et exemples autorisés depuis les sources réelles, en lecture seule.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import sqlglot
from sqlglot import exp

from .config import HERE, SOURCES

SENSITIVE = {
    "national_number",
    "iban",
    "street_address",
    "birth_date",
    "work_email",
    "contrepartie_iban",
}
IDENTITIES = {
    "last_name",
    "first_name",
    "employee_id",
    "manager_id",
    "payslip_id",
    "contract_id",
    "salary_id",
    "line_id",
    "work_email",
}
COMPENSATION = {"salary_history", "payslips", "payslip_lines"}

ERP_DESCRIPTIONS = {
    "SOC_SITE": "Sites de l'entreprise",
    "PAR_CODE": "Codes métier et libellés : types, statuts et motifs",
    "ART_FAMILLE": "Familles d'articles et comptes comptables",
    "ART_ARTICLE": "Articles, produits finis, pièces et prestations",
    "ART_TARIF": "Tarifs par période et exceptions par client",
    "ART_NOMENC": "Composants de la nomenclature de fabrication",
    "CLI_CLIENT": "Référentiel des clients",
    "FRN_FOURNISSEUR": "Fournisseurs d'articles",
    "VDR_VENDEUR": "Commerciaux et matricules de paie",
    "VTE_CDE": "En-têtes des commandes clients",
    "VTE_CDE_LIG": "Lignes des commandes clients",
    "VTE_FACT": "En-têtes des factures F et avoirs A, montants stockés positifs",
    "VTE_FACT_LIG": "Lignes des factures et avoirs",
    "ACH_CDE": "Commandes fournisseurs",
    "ACH_CDE_LIG": "Lignes des commandes fournisseurs",
    "ACH_RECEP": "Réceptions fournisseurs",
    "ACH_RECEP_LIG": "Lignes reçues et lots",
    "ACH_FACT": "Factures des fournisseurs d'articles",
    "PRD_OF": "Ordres de fabrication par produit, semaine et ligne",
    "STK_MVT": "Mouvements de stock : quantités déjà signées",
    "STK_ETAT": "Photographie du stock au 31 mai 2026",
    "LOG_TRANSP": "Transporteurs",
    "LOG_EXPED": "Expéditions et bons de livraison",
}


def build_catalog(sql_dir: Path) -> dict:
    """Extrait les 51 tables sans exécuter les scripts et sans lire leurs lignes."""
    catalog = {"sources": {}, "source_fingerprints": {}}
    names = {
        "erp": "01_erp_gespro_sqlserver.sql",
        "compta": "02_compta_postgres.sql",
        "paie": "03_paie_postgres.sql",
    }
    for source, filename in names.items():
        path = sql_dir / filename
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        catalog["source_fingerprints"][filename] = hashlib.sha256(raw).hexdigest()
        tables = {}
        for match in re.finditer(r"^CREATE TABLE\s+.*?^\);", text, re.M | re.S):
            node = sqlglot.parse_one(match.group(), read=SOURCES[source]["dialect"])
            schema = node.this
            table = schema.this.name
            columns, primary = {}, []
            for item in schema.expressions:
                if isinstance(item, exp.ColumnDef):
                    columns[item.name] = {"type": item.kind.sql(), "description": ""}
                for key in item.find_all(exp.PrimaryKey):
                    primary.extend(
                        (c.this if isinstance(c, exp.Ordered) else c).name
                        for c in key.expressions
                    )
            tables[table] = {
                "name": table,
                "description": ERP_DESCRIPTIONS.get(table, ""),
                "columns": columns,
                "primary_key": primary,
                "foreign_keys": [],
            }
            if source == "erp":
                tables[table]["description_origin"] = (
                    "Description ajoutée par IA d'après la présentation ; aucun commentaire ERP natif"
                )
        for match in re.finditer(
            r"COMMENT ON (TABLE|COLUMN) ([\w.]+) IS '((?:[^']|'')*)';", text
        ):
            kind, target, description = match.groups()
            description = description.replace("''", "'")
            if kind == "TABLE" and target in tables:
                tables[target]["description"] = description
            elif kind == "COLUMN":
                table, column = target.rsplit(".", 1)
                if table in tables and column in tables[table]["columns"]:
                    tables[table]["columns"][column]["description"] = description
        # Les FK sont déclarées après les CREATE TABLE dans les scripts officiels.
        for match in re.finditer(
            r"ALTER TABLE\s+([\w.\[\]]+)\s+ADD CONSTRAINT\s+\S+\s+FOREIGN KEY\s*\(([^)]+)\)\s+REFERENCES\s+([\w.\[\]]+)\s*\(([^)]+)\)",
            text,
            re.I,
        ):
            src, cols, dst, targets = match.groups()

            def clean(v):
                return v.replace("[", "").replace("]", "").split(".")[-1].strip()

            src, dst = clean(src), clean(dst)
            if src in tables:
                tables[src]["foreign_keys"].append(
                    {
                        "columns": [clean(v) for v in cols.split(",")],
                        "target_table": dst,
                        "target_columns": [clean(v) for v in targets.split(",")],
                    }
                )
        for table in tables.values():
            table["restricted_columns"] = [
                c for c in table["columns"] if c.casefold() in SENSITIVE
            ]
        catalog["sources"][source] = {**SOURCES[source], "tables": tables}
    return catalog


def load_catalog(path: Path | None = None) -> dict:
    return json.loads((path or HERE / "ontology" / "catalog.json").read_text())


def table_definition(catalog: dict, source: str, table: str) -> dict:
    """Résout un nom de table simple, sans autoriser de SQL dans un identifiant."""
    if source not in catalog["sources"]:
        raise ValueError("Source inconnue ; appeler list_sources")
    for name, definition in catalog["sources"][source]["tables"].items():
        if name.casefold() == table.casefold():
            return definition
    raise ValueError(f"Table inconnue dans {source}: {table}")
