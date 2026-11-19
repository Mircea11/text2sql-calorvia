"""Validation SQL par AST : dialecte, catalogue, fonctions, confidentialité, limite.

L'exécution revalide toujours le SQL : un appel antérieur à validate_sql ne vaut
pas autorisation. Les privilèges agent_ro constituent une couche indépendante.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from .catalog import COMPENSATION, IDENTITIES, SENSITIVE
from .config import SOURCES

SAFE_FUNCTIONS = {
    "ABS",
    "AND",
    "OR",
    "NOT",
    "AVG",
    "CASE",
    "CAST",
    "CEIL",
    "COALESCE",
    "CONCAT",
    "COUNT",
    "CURRENT_DATE",
    "DATE_ADD",
    "DATE_DIFF",
    "DATE_FROM_PARTS",
    "DATE_TRUNC",
    "DAY",
    "EXTRACT",
    "FLOOR",
    "IF",
    "LEFT",
    "LENGTH",
    "LOWER",
    "LTRIM",
    "MAX",
    "MIN",
    "MONTH",
    "NULLIF",
    "REPLACE",
    "RIGHT",
    "ROUND",
    "RTRIM",
    "SUBSTRING",
    "SUM",
    "TIME_TO_STR",
    "TO_CHAR",
    "TRIM",
    "TRY_CAST",
    "UPPER",
    "YEAR",
}
PAYROLL_DIMENSIONS = {
    "period_month",
    "site_code",
    "department_code",
    "cost_center_code",
    "element_code",
    "gl_account",
    "category",
    "contract_type",
    "run_type",
    "run_id",
    "name",
    "label",
    "valid_from",
    "payment_date",
}


def validate(source: str, sql: str, catalog: dict, max_rows: int = 200) -> dict:
    """Retourne un SQL borné ou une erreur exploitable par l'agent, sans exécution."""
    try:
        if source not in SOURCES:
            raise ValueError("Source inconnue")
        if not sql.strip() or len(sql) > 24000:
            raise ValueError("Requête vide ou trop longue")
        dialect = SOURCES[source]["dialect"]
        statements = [x for x in sqlglot.parse(sql, read=dialect) if x is not None]
        if len(statements) != 1 or not isinstance(
            statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)
        ):
            raise ValueError("Une seule instruction SELECT est autorisée")
        tree = statements[0]
        forbidden = (exp.DML, exp.DDL, exp.Into, exp.Command, exp.Lock, exp.StarMap)
        if any(isinstance(n, forbidden) for n in tree.walk()):
            raise ValueError("Écriture, verrouillage ou commande interdite")
        if any(w.args.get("recursive") for w in tree.find_all(exp.With)):
            raise ValueError("CTE récursive non autorisée")
        for func in tree.find_all(exp.Func):
            name = (
                func.name.upper()
                if isinstance(func, exp.Anonymous)
                else func.sql_name().upper()
            )
            if name not in SAFE_FUNCTIONS:
                raise ValueError(f"Fonction non autorisée: {name}")
        actual_tables = []
        definitions = catalog["sources"][source]["tables"]
        lower_names = {n.casefold(): n for n in definitions}
        for scope in traverse_scope(tree):
            for table in scope.tables:
                if table.name in scope.cte_sources:
                    continue
                if table.catalog or (
                    table.db and table.db.casefold() != SOURCES[source]["schema"]
                ):
                    raise ValueError("Autre base ou schéma non autorisé")
                if table.name.casefold() not in lower_names:
                    raise ValueError(f"Table inconnue: {table.name}")
                actual_tables.append(lower_names[table.name.casefold()])
        schema = {
            name: {c: v["type"] for c, v in definition["columns"].items()}
            for name, definition in definitions.items()
        }
        qualified = qualify(
            tree.copy(),
            dialect=dialect,
            schema=schema,
            identify=False,
            quote_identifiers=False,
            validate_qualify_columns=True,
        )
        for column in qualified.find_all(exp.Column):
            if column.name.casefold() in SENSITIVE:
                raise ValueError("Colonne personnelle interdite")
        if source == "paie":
            for column in qualified.find_all(exp.Column):
                if column.name.casefold() in {
                    "first_name",
                    "last_name",
                    "work_email",
                    "birth_date",
                    "pdf_path",
                    "national_number",
                    "iban",
                    "street_address",
                }:
                    raise ValueError(
                        "Identité individuelle masquée ; utiliser des agrégats par site ou période"
                    )
            if any(t.casefold() in COMPENSATION for t in actual_tables):
                for select in qualified.find_all(exp.Select):
                    # Pas de ligne individuelle, de compensation conditionnelle par personne,
                    # ni de groupe par matricule. Une jointure de clés reste possible.
                    if not any(
                        isinstance(n, exp.AggFunc)
                        for item in select.expressions
                        for n in item.walk()
                    ):
                        raise ValueError(
                            "Paie: seules les rémunérations agrégées sont autorisées"
                        )
                    for column in select.find_all(exp.Column):
                        if column.name.casefold() in IDENTITIES:
                            parent = column.parent
                            allowed_join = (
                                isinstance(parent, exp.EQ)
                                and isinstance(parent.left, exp.Column)
                                and isinstance(parent.right, exp.Column)
                                and parent.find_ancestor(exp.Join) is not None
                            )
                            allowed_count = isinstance(parent, exp.Count) or (
                                isinstance(parent, exp.Distinct)
                                and isinstance(parent.parent, exp.Count)
                            )
                            if not (allowed_join or allowed_count):
                                raise ValueError(
                                    "Paie individuelle interdite, y compris par filtre ou sous-requête"
                                )
                    group = select.args.get("group")
                    if group and any(
                        c.name.casefold() not in PAYROLL_DIMENSIONS
                        for c in group.find_all(exp.Column)
                    ):
                        raise ValueError("Regroupement de paie trop détaillé")
                # Une somme pour un site d'une personne reste individuelle.
                measures = {
                    "gross_amount",
                    "net_amount",
                    "employer_onss",
                    "employee_onss",
                    "onss_employee",
                    "taxable_amount",
                    "withholding_tax",
                    "monthly_gross",
                    "hourly_rate",
                    "amount",
                    "rate",
                    "quantity",
                }
                if any(
                    c.name.casefold() in measures
                    for c in qualified.find_all(exp.Column)
                ):
                    if (
                        not isinstance(tree, exp.Select)
                        or len(list(tree.find_all(exp.Select))) != 1
                    ):
                        raise ValueError(
                            "Paie: utiliser une agrégation simple, sans sous-requête ni UNION"
                        )
                    carriers = [
                        t
                        for t in tree.find_all(exp.Table)
                        if t.name.casefold() in {"payslips", "salary_history"}
                    ]
                    if not carriers:
                        raise ValueError(
                            "Paie: joindre payslips pour contrôler le nombre de personnes"
                        )
                    allowed = PAYROLL_DIMENSIONS | measures | IDENTITIES
                    if any(
                        c.name.casefold() not in allowed
                        for c in qualified.find_all(exp.Column)
                    ):
                        raise ValueError(
                            "Paie: filtre ou attribut personnel non autorisé dans une rémunération"
                        )
                    carrier = carriers[0].alias_or_name
                    count = exp.Count(
                        this=exp.Distinct(
                            expressions=[exp.column("employee_id", table=carrier)]
                        )
                    )
                    tree = tree.having(
                        exp.GTE(this=count, expression=exp.Literal.number(5)),
                        append=True,
                    )
        # Conserver le SQL soumis, après validation des colonnes ; pas de réécriture
        # des calculs métier par l'optimiseur de qualification.
        existing = tree.args.get("limit")
        limit = max_rows
        if existing:
            value = existing.expression
            if not isinstance(value, exp.Literal) or not value.is_int:
                raise ValueError("Limite de lignes entière obligatoire")
            limit = min(max_rows, int(value.this))
            if limit <= 0:
                raise ValueError("Limite de lignes positive obligatoire")
        tree = tree.limit(limit)
        return {
            "valid": True,
            "source": source,
            "sql": tree.sql(dialect=dialect),
            "limit": limit,
            "tables": sorted(set(actual_tables)),
        }
    except (ValueError, sqlglot.errors.SqlglotError) as exc:
        return {"valid": False, "error": str(exc)[:1000], "source": source}
