"""Calculs financiers contrôlés et exécutés par le MCP.

Les périodes viennent de la question. Aucun résultat attendu n'est chargé ici.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


MONTHS = (
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
)
_MONTH = "|".join(MONTHS)
_PERIOD = rf"(?P<month>{_MONTH}) (?P<year>20\d{{2}})"
_DAY = rf"(?P<day>\d{{1,2}})(?:er)? {_PERIOD}"
_SNAPSHOT = date(2026, 5, 31)
_ACCOUNTING_JOIN = "FROM ligne_ecriture l JOIN ecriture e ON e.id_ecriture = l.id_ecriture"
_EBITDA = (
    "(l.numero_compte LIKE '7%' AND l.numero_compte NOT LIKE '79%') "
    "OR l.numero_compte LIKE '60%' OR l.numero_compte LIKE '61%' OR l.numero_compte LIKE '62%'"
)
_REVENUE = "l.numero_compte LIKE '70%'"
_NET = (
    "(l.numero_compte LIKE '6%' AND l.numero_compte NOT LIKE '69%') OR "
    "(l.numero_compte LIKE '7%' AND l.numero_compte NOT LIKE '79%')"
)


@dataclass(frozen=True)
class Measure:
    source: str
    sql: str
    label: str


@dataclass(frozen=True)
class MetricPlan:
    measures: tuple[Measure, ...]
    period: str
    unit: str = "€"
    difference: bool = False
    group_label: str = ""
    columns: tuple[str, ...] = ()

    def render(self, results: list[dict]) -> str:
        if self.columns:
            result, = results
            rows = result.get("rows", [])
            if (
                not result.get("valid")
                or result.get("truncated")
                or len(rows) != 1
                or len(rows[0]) != len(self.columns)
            ):
                return "Je n’ai pas pu identifier une ligne de livraison unique pour ces critères."
            quantity, received = rows[0]
            if quantity is None:
                return "La quantité manquante n’est pas renseignée."
            formatted_quantity = _format_decimal(Decimal(str(quantity)), 0)
            values = (formatted_quantity, received)
            return "\n".join(
                f"{label} : **{value}**." if value is not None else f"{label} : non renseigné."
                for label, value in zip(self.columns, values, strict=True)
            )
        if self.group_label:
            result, = results
            if not result.get("valid") or result.get("truncated") or not result.get("rows"):
                return "Je n’ai pas obtenu de ventilation vérifiable pour le calcul demandé."
            values = ", ".join(f"{group} : {count} {self.unit}" for group, count in result["rows"])
            return f"{self.group_label} ({self.period}) : {values}."
        values = []
        for result in results:
            rows = result.get("rows", [])
            if (
                not result.get("valid") or result.get("truncated")
                or len(rows) != 1 or len(rows[0]) != 1 or rows[0][0] is None
            ):
                return "Je n’ai pas obtenu de valeur vérifiable pour le calcul demandé."
            values.append(Decimal(str(rows[0][0])))

        precision = 2 if self.unit in {"€", "%", "ETP"} else None
        lines = [
            f"{measure.label} ({self.period}) : **{_format_decimal(value, precision)} {self.unit}**."
            for measure, value in zip(self.measures, values, strict=True)
        ]
        if self.difference:
            delta = (values[0] - values[1]).quantize(Decimal("0.01"))
            lines.append(
                f"Écart ({self.measures[0].source} moins {self.measures[1].source}) : "
                f"**{_format_decimal(delta, 2)} €**. Les montants "
                f"{'concordent' if delta == 0 else 'diffèrent'}."
            )
        return "\n".join(lines)


def _format_decimal(value: Decimal, precision: int | None) -> str:
    rendered = f"{value:,.{precision}f}" if precision is not None else f"{value:,f}"
    if precision is None and "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered.translate(str.maketrans({",": "\u202f", ".": ","}))


def _normalized(question: str) -> str:
    text = unicodedata.normalize("NFKD", question.casefold().replace("’", "'"))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).strip(" ?.!").split())


def clarify_scope(question: str) -> str | None:
    q = _normalized(question)
    if re.fullmatch(r"(?:quel est le |quel )?chiffre d'affaires (?:de |en )?(?:" + _MONTH + r")", q):
        return "Pour quelle année ? Souhaitez-vous le chiffre d’affaires facturé dans l’ERP ou le chiffre d’affaires comptabilisé ?"
    if re.fullmatch(r"combien (?:de personnes|d'employes) (?:avons-nous|y a-t-il)", q):
        return "À quelle date et sur quel périmètre (tous sites ou un site précis) ? Souhaitez-vous un nombre de personnes ou des ETP ?"
    if re.fullmatch(r"(?:quel est le )?stock (?:actuel|disponible)", q):
        return "Quel article, quel site et quelle date souhaitez-vous ? La photographie des stocks est au 31 mai 2026."
    periods = list(re.finditer(rf"\b{_PERIOD}\b", q))
    if len(periods) == 1 and re.search(r"\b(chiffre d'affaires|ebitda|paie|factures?|stock|ventes)\b", q):
        period = periods[0]
        if date(int(period["year"]), MONTHS.index(period["month"]) + 1, 1) > _SNAPSHOT:
            return "La période demandée est postérieure à l’extraction du 31 mai 2026. Les données de cette période ne sont pas disponibles."
    return None


def _accounting(period: str, condition: str, label: str, expression: str = "l.credit-l.debit") -> Measure:
    return Measure(
        "compta",
        f"SELECT SUM({expression}) AS montant {_ACCOUNTING_JOIN} "
        f"WHERE e.code_periode LIKE '{period}' AND ({condition})",
        label,
    )


def _erp_revenue(start: date, stop: date, kind: str = "net") -> Measure:
    if kind == "avoir":
        value = "FAC_MT_HT"
        filter_type = " AND FAC_TYPE = 'A'"
        label = "Avoirs HT"
    else:
        value = "CASE WHEN FAC_TYPE = 'A' THEN -FAC_MT_HT ELSE FAC_MT_HT END"
        filter_type = ""
        label = "Chiffre d’affaires net facturé HT"
    return Measure(
        "erp", f"SELECT SUM({value}) AS montant FROM VTE_FACT "
        f"WHERE FAC_DT >= '{start}' AND FAC_DT < '{stop}'{filter_type}", label,
    )


def _payroll(start: date, column: str, label: str) -> Measure:
    return Measure(
        "paie",
        f"SELECT SUM(p.{column}) AS montant FROM payslips p "
        f"JOIN payroll_runs r ON r.run_id = p.run_id WHERE r.period_month = '{start}'",
        label,
    )


def _headcount(q: str) -> MetricPlan | None:
    count = re.fullmatch(
        rf"combien (?:de personnes sont sous contrat|d'etp contractuels sont actifs) au {_DAY}(?:, par site)?", q,
    )
    if not count or (as_of := _match_date(count)) is None:
        return None
    where = f"WHERE c.start_date <= '{as_of}' AND (c.end_date IS NULL OR c.end_date >= '{as_of}')"
    if "d'etp" in q:
        if q.endswith("par site"):
            return None
        sql = f"SELECT SUM(c.work_regime) AS etp FROM contracts c {where}"
        return MetricPlan((Measure("paie", sql, "ETP contractuels"),), str(as_of), "ETP")
    if q.endswith("par site"):
        sql = (
            "SELECT d.site_code, COUNT(DISTINCT c.employee_id) AS personnes FROM contracts c "
            f"JOIN departments d ON d.department_code = c.department_code {where} "
            "GROUP BY d.site_code ORDER BY d.site_code"
        )
        return MetricPlan((Measure("paie", sql, "Effectif"),), str(as_of), "personnes", group_label="Effectif par site")
    sql = f"SELECT COUNT(DISTINCT c.employee_id) AS personnes FROM contracts c {where}"
    return MetricPlan((Measure("paie", sql, "Effectif"),), str(as_of), "personnes")


def _inventory_counts(q: str) -> MetricPlan | None:
    # Les sujets désignent des ensembles complets, sans filtre implicite.
    counts = (
        (r"factures et avoirs (?:sont presents|figurent) dans l'extraction erp", "erp", "VTE_FACT", "factures et avoirs"),
        (r"clients (?:contient l'erp|sont presents dans l'extraction erp)", "erp", "CLI_CLIENT", "clients"),
        (r"ecritures comptables contient l'extraction", "compta", "ecriture", "écritures comptables"),
        (r"journaux comptables sont definis", "compta", "journal", "journaux comptables"),
        (r"fiches de paie (?:figurent|sont presentes) dans l'extraction", "paie", "payslips", "fiches de paie"),
    )
    subject = re.fullmatch(r"combien (?:de |d')(.+)", q)
    if subject:
        for pattern, source, table, unit in counts:
            if re.fullmatch(pattern, subject[1]):
                return MetricPlan((Measure(source, f"SELECT COUNT(*) AS nombre FROM {table}", "Total"),), "extraction", unit)
    return None


def _erp_operations(question: str, q: str) -> MetricPlan | None:
    initial = re.fullmatch(rf"combien de mouvements de stock initiaux ont ete repris au {_DAY}", q)
    if initial:
        as_of = _match_date(initial)
        if as_of is not None:
            sql = (
                "SELECT COUNT(*) AS mouvements FROM STK_MVT "
                f"WHERE MVT_TYPE = 'INIT' AND MVT_DT >= '{as_of}' "
                f"AND MVT_DT < DATEADD(day, 1, CAST('{as_of}' AS date))"
            )
            return MetricPlan((Measure("erp", sql, "Mouvements initiaux"),), str(as_of), "mouvements")

    raw = " ".join(question.casefold().strip(" ?.!").split())
    stock = re.fullmatch(
        r"combien (?:de |d')(?P<article>[^\W_][^\W_ -]*(?:[ -][^\W_]+)*) sont en stock, tous sites confondus, au 31 mai 2026", raw,
    )
    if stock and len(stock["article"]) <= 60:
        article = stock["article"].strip()
        sql = (
            "SELECT SUM(s.STK_QTE) AS quantite FROM STK_ETAT s "
            "JOIN ART_ARTICLE a ON a.ART_ID = s.ART_ID "
            f"WHERE a.ART_CODE = N'{article}' OR a.ART_LIB LIKE N'%{article}%'"
            " HAVING COUNT(DISTINCT a.ART_ID) = 1"
        )
        return MetricPlan((Measure("erp", sql, "Stock total"),), str(_SNAPSHOT), "unités")

    lot = re.fullmatch(
        r"combien (?:de vannes|d'unites) du lot (?P<lot>[a-z0-9-]{1,35}) "
        r"ont ete recues et retournees au fournisseur", q,
    )
    if lot:
        code = lot["lot"].upper()
        received = Measure("erp", f"SELECT SUM(RL_QTE_RECUE) AS recues FROM ACH_RECEP_LIG WHERE RL_LOT = '{code}'", "Quantité reçue")
        returned = Measure("erp", f"SELECT -SUM(MVT_QTE) AS retournees FROM STK_MVT WHERE MVT_LOT = '{code}' AND MVT_TYPE = 'RET'", "Quantité retournée")
        return MetricPlan((received, returned), f"lot {code}", "unités")

    units = re.fullmatch(
        rf"combien d'unites de produits finis ont ete facturees a (?P<client>[a-z0-9 -]{{2,60}}?) "
        rf"de (?P<start>{_MONTH}) a {_PERIOD}, hors avoirs", q,
    )
    if units:
        year = int(units["year"])
        start_month = MONTHS.index(units["start"]) + 1
        end_month = MONTHS.index(units["month"]) + 1
        if start_month > end_month:
            return None
        start = date(year, start_month, 1)
        stop = date(year + (end_month == 12), end_month % 12 + 1, 1)
        sql = (
            "SELECT SUM(l.FL_QTE) AS unites FROM VTE_FACT f "
            "JOIN VTE_FACT_LIG l ON l.FAC_ID = f.FAC_ID "
            "JOIN ART_ARTICLE a ON a.ART_ID = l.ART_ID JOIN CLI_CLIENT c ON c.CLI_ID = f.CLI_ID "
            f"WHERE c.CLI_NOM LIKE N'%{units['client']}%' AND a.ART_TYPE = 'PF' "
            f"AND f.FAC_TYPE = 'F' AND f.FAC_DT >= '{start}' AND f.FAC_DT < '{stop}'"
        )
        return MetricPlan((Measure("erp", sql, "Unités de produits finis facturées"),), f"{units['start']} à {units['month']} {year}", "unités")

    delivery = re.fullmatch(
        rf"combien de compresseurs manquaient a la livraison (?P<supplier>[a-z0-9 -]{{2,60}}?) du {_DAY}, et quand sont-ils arrives", q,
    )
    if delivery and (as_of := _match_date(delivery)):
        sql = (
            f"SELECT l.ACL_QTE - SUM(CASE WHEN r.REC_DT = '{as_of}' THEN rl.RL_QTE_RECUE ELSE 0 END) AS manquants, "
            f"MIN(CASE WHEN r.REC_DT > '{as_of}' THEN r.REC_DT END) AS arrivee "
            "FROM ACH_CDE c JOIN FRN_FOURNISSEUR f ON f.FRN_ID = c.FRN_ID "
            "JOIN ACH_CDE_LIG l ON l.AC_ID = c.AC_ID JOIN ART_ARTICLE a ON a.ART_ID = l.ART_ID "
            "JOIN ACH_RECEP r ON r.AC_ID = c.AC_ID "
            "JOIN ACH_RECEP_LIG rl ON rl.REC_ID = r.REC_ID AND rl.ACL_ID = l.ACL_ID "
            f"WHERE f.FRN_NOM LIKE N'%{delivery['supplier']}%' AND c.AC_DT_LIV_PREV = '{as_of}' "
            "AND a.ART_LIB LIKE N'Compresseur%' GROUP BY l.ACL_ID, l.ACL_QTE"
        )
        measure = Measure("erp", sql, "Écart de livraison")
        return MetricPlan((measure,), str(as_of), columns=("Compresseurs manquants", "Réception suivante"))
    return None


def _match_date(match: re.Match) -> date | None:
    try:
        return date(int(match["year"]), MONTHS.index(match["month"]) + 1, int(match["day"]))
    except ValueError:
        return None


def plan_metric(question: str) -> MetricPlan | None:
    """Les formes non reconnues restent dans la boucle générale de l'agent."""
    q = _normalized(question)
    if plan := _headcount(q) or _inventory_counts(q) or _erp_operations(question, q):
        return plan
    annual = re.fullmatch(
        r"(?:quel est le )?resultat net (?:de l'exercice )?(20\d{2}) avant affectation", q,
    )
    if annual:
        year = annual[1]
        return MetricPlan((_accounting(year + "-%", _NET, "Résultat net avant affectation"),), year)
    annual = re.fullmatch(r"(?:combien d'|total des )amortissements (?:ont ete comptabilises )?en (20\d{2})", q)
    if annual:
        year = annual[1]
        measure = Measure("compta", f"SELECT SUM(montant) AS montant FROM amortissement WHERE code_periode LIKE '{year}-%'", "Amortissements comptabilisés")
        return MetricPlan((measure,), year)
    annual = re.fullmatch(r"(?:quel est le )?budget final (?:de )?(20\d{2})(?:, toutes periodes et tous comptes confondus)?", q)
    if annual:
        year = annual[1]
        measure = Measure("compta", f"SELECT SUM(montant) AS montant FROM budget WHERE code_exercice = '{year}' AND version = 'FINAL'", "Budget FINAL")
        return MetricPlan((measure,), year)

    match = re.fullmatch(
        rf"(?:quel(?:le)? est (?:le |la |l')?)?(?P<metric>"
        r"marge (?:d'|d |de l')ebitda|ebitda|chiffre d'affaires net facture ht|"
        r"chiffre d'affaires comptabilise|total des salaires bruts des fiches de paie|"
        r"total des cotisations patronales des fiches de paie"
        rf") (?:de |en |d')?{_PERIOD}(?: en pourcentage| selon la convention du laboratoire)?",
        q,
    )
    cross = re.fullmatch(
        rf"le chiffre d'affaires net facture et le chiffre d'affaires comptabilise de {_PERIOD}"
        r" sont-ils identiques \? calcule l'ecart erp moins comptabilite", q,
    )
    credit = re.fullmatch(
        rf"quel montant ht total d'avoirs a ete emis en {_PERIOD}, exprime positivement", q,
    )
    staffing = re.fullmatch(
        rf"combien de jours (?P<kind>de teletravail ont ete prestes|ouvres d'absence pour accident du travail ont ete enregistres) en {_PERIOD}", q,
    )
    payroll_cross = re.fullmatch(
        rf"(?:les salaires bruts de {_PERIOD} dans la paie correspondent-ils aux remunerations comptabilisees sur les comptes 620 \?"
        r"|compare les cotisations patronales de (?P<onss_month>" + _MONTH + r") (?P<onss_year>20\d{2}) en paie avec les comptes comptables 621 et)"
        r" calcule l'ecart comptabilite moins paie", q,
    )
    if not (period_match := match or cross or credit or staffing or payroll_cross):
        return None
    parts = period_match.groupdict()
    month = MONTHS.index(parts["month"] or parts.get("onss_month")) + 1
    year = int(parts["year"] or parts.get("onss_year"))
    start = date(year, month, 1)
    stop = date(year + (month == 12), month % 12 + 1, 1)
    period = start.strftime("%Y-%m")
    if staffing:
        remote = staffing["kind"].startswith("de teletravail")
        condition = "work_location = 'TELE'" if remote else "absence_code = 'ACC'"
        label = "Jours de télétravail" if remote else "Jours ouvrés d’absence pour accident du travail"
        sql = f"SELECT COUNT(*) AS jours FROM timesheets WHERE {condition} AND work_date >= '{start}' AND work_date < '{stop}'"
        return MetricPlan((Measure("paie", sql, label),), period, "jours")
    if payroll_cross:
        onss = bool(parts.get("onss_month"))
        account = "621" if onss else "620"
        label = "Cotisations patronales" if onss else "Salaires bruts"
        account_total = _accounting(period, f"l.numero_compte LIKE '{account}%'", label + " en comptabilité", "l.debit-l.credit")
        payroll_total = _payroll(start, "employer_onss" if onss else "gross_amount", label + " en paie")
        return MetricPlan((account_total, payroll_total), period, difference=True)
    if cross:
        return MetricPlan(
            (_erp_revenue(start, stop), _accounting(period, _REVENUE, "Chiffre d’affaires comptabilisé")),
            period,
            difference=True,
        )
    if credit:
        return MetricPlan((_erp_revenue(start, stop, "avoir"),), period)
    name = match["metric"]
    if name.startswith("marge"):
        sql = (
            f"SELECT ROUND(100.0 * SUM(CASE WHEN {_EBITDA} THEN l.credit-l.debit ELSE 0 END) "
            f"/ NULLIF(SUM(CASE WHEN {_REVENUE} THEN l.credit-l.debit ELSE 0 END), 0), 2) AS marge_pct "
            f"{_ACCOUNTING_JOIN} WHERE e.code_periode = '{period}'"
        )
        return MetricPlan((Measure("compta", sql, "Marge d’EBITDA"),), period, "%")
    if name == "ebitda":
        return MetricPlan((_accounting(period, _EBITDA, "EBITDA"),), period)
    if name == "chiffre d'affaires net facture ht":
        return MetricPlan((_erp_revenue(start, stop),), period)
    if name == "chiffre d'affaires comptabilise":
        return MetricPlan((_accounting(period, _REVENUE, "Chiffre d’affaires comptabilisé"),), period)
    column, label = (
        ("gross_amount", "Total des salaires bruts")
        if "salaires bruts" in name
        else ("employer_onss", "Total des cotisations patronales")
    )
    return MetricPlan((_payroll(start, column, label),), period)
