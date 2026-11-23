from text2sql.catalog import load_catalog
from text2sql.metrics import clarify_scope, plan_metric
from text2sql.validation import validate


def _result(value, *, truncated=False):
    return {"valid": True, "rows": [[value]], "truncated": truncated}


def test_ebitda_margin_uses_explicit_month_and_approved_accounts():
    plan = plan_metric("Marge d’EBITDA de février 2026")
    measure, = plan.measures
    assert measure.source == "compta"
    assert "'2026-02'" in measure.sql
    assert all(f"OR l.numero_compte LIKE '{account}%'" in measure.sql for account in (60, 61, 62))
    assert "l.numero_compte LIKE '70%'" in measure.sql
    assert validate(measure.source, measure.sql, load_catalog())["valid"]


def test_revenue_uses_half_open_range_without_invoice_status_filter():
    plan = plan_metric("Chiffre d’affaires net facturé HT d’avril 2026")
    measure, = plan.measures
    assert "FAC_DT >= '2026-04-01' AND FAC_DT < '2026-05-01'" in measure.sql
    assert "-FAC_MT_HT" in measure.sql
    assert "FAC_STATUT" not in measure.sql
    assert plan_metric("Chiffre d’affaires net facturé HT d’avril 2026 par client") is None


def test_difference_and_conclusion_follow_the_same_values():
    plan = plan_metric(
        "Le chiffre d’affaires net facturé et le chiffre d’affaires comptabilisé de février 2026 "
        "sont-ils identiques ? Calcule l’écart ERP moins comptabilité."
    )
    equal = plan.render([_result("113.00"), _result("113")])
    assert "0,00 €" in equal and "concordent" in equal
    unequal = plan.render([_result("112.35"), _result("113")])
    assert "-0,65 €" in unequal and "diffèrent" in unequal


def test_missing_or_truncated_value_cannot_be_presented_as_zero():
    plan = plan_metric("EBITDA en février 2026")
    assert "valeur vérifiable" in plan.render([_result(None)])
    assert "valeur vérifiable" in plan.render([_result("99", truncated=True)])


def test_clarification_requests_missing_scope_and_identifies_future_period():
    assert "année" in clarify_scope("Chiffre d’affaires de février ?")
    assert "ETP" in clarify_scope("Combien d’employés y a-t-il ?")
    assert "postérieure" in clarify_scope("EBITDA de janvier 2028 ?")
    assert clarify_scope("EBITDA de février 2026 ?") is None
