"""Vérification CPU des données fournies, SANS remplacer les moteurs du rendu.

Construit trois copies DuckDB hors Git pour vérifier les requêtes de référence.
Ne prouve ni les privilèges PostgreSQL/SQL Server ni le comportement du LLM.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp

from .config import SOURCES


def verify_manifest(sql_dir: Path, destination: Path) -> None:
    """Refuse la réutilisation d'une copie dont les scripts sources ont changé."""
    manifest = json.loads((destination / "manifest.json").read_text())
    files = {
        "erp": "01_erp_gespro_sqlserver.sql",
        "compta": "02_compta_postgres.sql",
        "paie": "03_paie_postgres.sql",
    }
    for source, filename in files.items():
        if (
            hashlib.sha256((sql_dir / filename).read_bytes()).hexdigest()
            != manifest["sources"][source]["sha256"]
        ):
            raise ValueError(
                f"Copie CPU périmée pour {source} ; préserver l'ancienne et utiliser un nouveau répertoire"
            )
        with duckdb.connect(
            str(destination / f"{source}.duckdb"), read_only=True
        ) as con:
            for table, expected in manifest["sources"][source]["row_counts"].items():
                if (
                    con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    != expected
                ):
                    raise ValueError(
                        f"Volume de copie CPU incohérent : {source}.{table}"
                    )


def strip_national_prefix(sql: str) -> str:
    """Retire N devant un littéral T-SQL, en respectant les apostrophes échappées."""
    out, quoted, i = [], False, 0
    while i < len(sql):
        if not quoted and sql[i : i + 2] == "N'":
            i += 1
        char = sql[i]
        out.append(char)
        if char == "'":
            if quoted and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("'")
                i += 1
            else:
                quoted = not quoted
        i += 1
    return "".join(out)


def copy_unescape(value: str):
    if value == r"\N":
        return None
    return re.sub(
        r"\\(.)",
        lambda m: {
            "t": "\t",
            "n": "\n",
            "r": "\r",
            "b": "\b",
            "f": "\f",
            "v": "\v",
            "\\": "\\",
        }.get(m[1], m[1]),
        value,
    )


def build_offline(sql_dir: Path, destination: Path) -> dict:
    """Charge les données officielles dans des copies locales identifiées par SHA256."""
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "erp": "01_erp_gespro_sqlserver.sql",
        "compta": "02_compta_postgres.sql",
        "paie": "03_paie_postgres.sql",
    }
    manifest = {"kind": "offline_data_verification_only", "sources": {}}
    for source, filename in files.items():
        target = destination / f"{source}.duckdb"
        if target.exists():
            raise FileExistsError(f"Copie existante préservée : {target}")
        text = (sql_dir / filename).read_text()
        con = duckdb.connect(str(target))
        con.execute("BEGIN")
        tables = []
        for match in re.finditer(r"^CREATE TABLE\s+.*?^\);", text, re.M | re.S):
            node = sqlglot.parse_one(match.group(), read=SOURCES[source]["dialect"])
            table = node.this.this
            table.set("db", None)
            tables.append(table.name)
            # Le parseur T-SQL représente les colonnes PK comme ORDERED ; DuckDB
            # n'accepte pas NULLS FIRST dans une contrainte de clé primaire.
            for key in node.find_all(exp.PrimaryKey):
                key.set(
                    "expressions",
                    [
                        c.this if isinstance(c, exp.Ordered) else c
                        for c in key.expressions
                    ],
                )
            for column in node.find_all(exp.ColumnDef):
                if source == "erp" and column.kind.sql().upper() == "BIT":
                    column.set("kind", exp.DataType.build("BOOLEAN"))
            con.execute(node.sql(dialect="duckdb"))
        if source == "erp":
            for match in re.finditer(
                r"^INSERT INTO .*?;(?=\r?\n|$)", text, re.M | re.S
            ):
                query = strip_national_prefix(match.group())
                head, values = query.split("VALUES", 1)
                head = re.sub(r"\[dbo\]\.\[([^]]+)\]", r'"\1"', head)
                head = re.sub(r"\[([^]]+)\]", r'"\1"', head)
                con.execute(head + "VALUES" + values)
        else:
            for match in re.finditer(
                r"^COPY (\w+) \(([^\n]+)\) FROM stdin;\n(.*?)^\\\.\s*$",
                text,
                re.M | re.S,
            ):
                table, columns, body = match.groups()
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".tsv", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
                    for line in body.splitlines():
                        values = [copy_unescape(v) for v in line.split("\t")]
                        writer.writerow([r"\N" if v is None else v for v in values])
                    f.flush()
                    con.execute(
                        f"COPY {table} ({columns}) FROM '{f.name}' (FORMAT CSV, DELIMITER '\t', NULL '\\N', HEADER FALSE)"
                    )
        con.execute("COMMIT")
        counts = {
            table: con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
        con.close()
        manifest["sources"][source] = {
            "sha256": hashlib.sha256((sql_dir / filename).read_bytes()).hexdigest(),
            "row_counts": counts,
        }
        print(
            f"Copie de vérification {source}: {len(tables)} tables, {sum(counts.values())} lignes",
            flush=True,
        )
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def reference_query(destination: Path, source: str, sql: str) -> dict:
    """Exécute un SELECT de référence revu, transpilé vers la copie CPU DuckDB."""
    tree = sqlglot.parse_one(sql, read=SOURCES[source]["dialect"])
    if not isinstance(tree, (exp.Select, exp.Union)) or any(
        isinstance(n, (exp.DML, exp.DDL, exp.Into)) for n in tree.walk()
    ):
        raise ValueError("Référence SELECT uniquement")
    for table in tree.find_all(exp.Table):
        table.set("db", None)
    with duckdb.connect(str(destination / f"{source}.duckdb"), read_only=True) as con:
        cursor = con.execute(tree.sql(dialect="duckdb"))
        columns = [c[0] for c in cursor.description]
        records = cursor.fetchall()
    return {
        "source": source,
        "sql": sql,
        "columns": columns,
        "rows": [[str(v) if v is not None else None for v in r] for r in records],
        "truncated": False,
    }
