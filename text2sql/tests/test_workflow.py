"""Vérifications de reprise, provenance, protection des groupes et données fournies."""

import json
import subprocess
import sys

import httpx
import pytest
import yaml

from text2sql import auto_ontology
from text2sql.catalog import build_catalog, load_catalog
from text2sql.config import ROOT, HERE
from text2sql.evaluation import numeric_score, compare_runs
from text2sql.offline import verify_manifest
from text2sql.runtime import exclusive_work
from text2sql.validation import validate


@pytest.mark.parametrize(
    "column",
    [
        "gross_amount",
        "net_amount",
        "employer_onss",
        "onss_employee",
        "taxable_amount",
        "withholding_tax",
    ],
)
def test_payroll_minimum_group_is_enforced_in_sql(column):
    result = validate("paie", f"SELECT SUM({column}) FROM payslips", load_catalog())
    assert result["valid"], result
    assert "HAVING COUNT(DISTINCT payslips.employee_id) >= 5" in result["sql"]


def test_payroll_subquery_cannot_bypass_cohort():
    assert not validate(
        "paie",
        "WITH p AS (SELECT SUM(gross_amount) AS amount FROM payslips) SELECT SUM(amount) FROM p",
        load_catalog(),
    )["valid"]


def test_native_draft_has_complete_relations_and_no_secret_columns():
    draft = auto_ontology.native_draft()
    tables = [
        t
        for d in draft["data_layer"]["databases"]
        for s in d["schemas"]
        for t in s["tables"]
    ]
    assert len(tables) == 51
    assert draft["semantic_layer"]["concepts"]
    assert draft["semantic_layer"]["semantic_fks"]
    assert all(
        not f["use_in_join_paths"] for f in draft["semantic_layer"]["semantic_fks"]
    )
    assert not {"iban", "national_number", "street_address"} & {
        c["name"] for t in tables for c in t["columns"]
    }


def test_model_yaml_workflow_mock_is_not_live_evidence(tmp_path, monkeypatch):
    """Vérifie les chemins HTTP réellement lus dans le code NVIDIA épinglé."""
    folder = tmp_path / "ontology"
    folder.mkdir()
    for name in ["catalog.json", "business.yaml"]:
        (folder / name).write_bytes((HERE / "ontology" / name).read_bytes())
    monkeypatch.setattr(auto_ontology, "HERE", tmp_path)
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "last_success_at": "before" if len(calls) == 1 else "after",
                    "running": False,
                },
            )
        if request.url.path.endswith("/export"):
            return httpx.Response(
                200, text=yaml.safe_dump(auto_ontology.native_draft())
            )
        return httpx.Response(200, json={"success": True})

    receipt = auto_ontology.generate(transport=httpx.MockTransport(handle))
    assert receipt["kind"] == "mock_contract_test"
    assert receipt["covered_tables"] == 51
    assert receipt["human_certification"] is False
    assert ("POST", "/api/model/import") in calls


def test_comparison_rejects_different_models(tmp_path):
    a = {"use_ontology": False, "model": "a"}
    b = {"use_ontology": True, "model": "b"}
    left = tmp_path / "a.json"
    right = tmp_path / "b.json"
    left.write_text(json.dumps(a))
    right.write_text(json.dumps(b))
    with pytest.raises(ValueError, match="model"):
        compare_runs(left, right)


def test_difference_required_for_cross_source_numeric_candidate():
    q = {
        "type": "cross_source",
        "references": [{"expected_rows": [["100.30"]]}, {"expected_rows": [["50.10"]]}],
    }
    assert not numeric_score(q, "100,30 euros et 50,10 euros")
    assert numeric_score(q, "100,30 euros et 50,10 euros : écart de 50,20 euros")


def test_lock_rejects_other_process_and_allows_nested_owner():
    with exclusive_work():
        with exclusive_work():
            code = "from text2sql.runtime import exclusive_work\nwith exclusive_work(): pass"
            result = subprocess.run(
                [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True
            )
            assert result.returncode != 0
            assert "déjà actif" in result.stderr


def test_official_files_and_cpu_cache_are_consistent():
    directory = ROOT / "data/text2sql/sources_calorvia/sql"
    if not directory.exists():
        pytest.skip(
            "Scripts officiels non présents ; ne pas substituer des données fictives"
        )
    actual = build_catalog(directory)
    assert actual == load_catalog()
    if not (ROOT / "data/text2sql/offline/manifest.json").exists():
        pytest.skip("Copies CPU non construites")
    verify_manifest(directory, ROOT / "data/text2sql/offline")
