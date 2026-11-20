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


def test_api_port_configuration(monkeypatch):
    from text2sql.config import Settings

    import uvicorn
    from text2sql import cli

    bound = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: bound.update(options))
    monkeypatch.setattr(sys, "argv", ["text2sql", "serve"])
    monkeypatch.setenv("T2SQL_API_PORT", "9017")
    cli.main()
    assert (bound["host"], bound["port"]) == ("127.0.0.1", 9017)
    assert Settings.load().api_port == 9017
    monkeypatch.setenv("T2SQL_API_PORT", "65536")
    with pytest.raises(ValueError, match="T2SQL_API_PORT"):
        Settings.load()


def test_interrupted_baseline_resumes_in_clean_worktree(tmp_path, monkeypatch):
    """Exerce la reprise sur un vrai dépôt temporaire ; modèle et journal simulés."""
    import asyncio
    import shutil
    from text2sql import evaluation, journal, runtime

    folder = tmp_path / "text2sql"
    (folder / "ontology").mkdir(parents=True)
    for name in ("business.yaml", "catalog.json"):
        shutil.copy(HERE / "ontology" / name, folder / "ontology" / name)
    (tmp_path / ".gitignore").write_text("data/\n")
    questions = [
        {"id": key, "type": "ambiguous", "question": key, "references": []}
        for key in ("A", "B")
    ]
    dataset = folder / "questions.json"
    dataset.write_text(json.dumps(questions))

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True)

    git("init", "-q")
    git("add", ".")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Références de test",
    )
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    monkeypatch.setattr(evaluation, "HERE", folder)
    monkeypatch.setattr(evaluation, "DATASET", dataset)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    monkeypatch.setenv("T2SQL_LLM_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.setenv("T2SQL_LLM_MODEL", "simulated")
    monkeypatch.setenv("T2SQL_JOURNAL_DSN", "host=127.0.0.1 dbname=simulated")
    monkeypatch.setattr(journal.Journal, "experiment", lambda self, payload: None)

    class Interruption(BaseException):
        pass

    calls = []

    async def model(question, **kwargs):
        calls.append(question)
        if calls == ["A", "B"]:
            raise Interruption()
        return {"answer": "Précisez la période."}

    monkeypatch.setattr(evaluation, "answer", model)
    with pytest.raises(Interruption):
        asyncio.run(evaluation.evaluate_live(False))
    (path,) = (tmp_path / "data/text2sql/runs").glob("*.json")
    assert [r["id"] for r in json.loads(path.read_text())["results"]] == ["A"]
    assert not git("status", "--porcelain")
    asyncio.run(evaluation.evaluate_live(False, resume=path))
    assert calls == ["A", "B", "B"]
    assert json.loads(path.read_text())["status"] == "completed"
    review = path.with_suffix(".csv")
    review.write_text("Revue humaine conservée\n")
    asyncio.run(evaluation.evaluate_live(False, resume=path))
    assert review.read_text() == "Revue humaine conservée\n"

def test_numeric_answer_after_sql():
    q = {"type": "simple", "references": [{"expected_rows": [["1320"]]}]}
    query = "```sql\nSELECT COUNT(*) FROM ecriture LIMIT 200\n```"
    assert numeric_score(q, query + "\nRésultat : 1 320 écritures.\n" + query)
    assert not numeric_score(q, "Résultat indisponible.\n```sql\nSELECT 1320\n```")
    assert not numeric_score(q, "Résultat indisponible.\n```sql\nSELECT 1320")
