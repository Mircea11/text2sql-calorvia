"""Format NVIDIA, provenance, couverture et contrôle avec/sans ontologie."""

import httpx
import pytest
import yaml

from text2sql import auto_ontology, runtime
from text2sql.auto_ontology import native_draft
from text2sql.catalog import load_catalog
from text2sql.config import Settings
from text2sql.ontology import context
from text2sql.sources import SourceService


def test_native_ontology_graph_has_valid_references_and_all_sources():
    document = native_draft()
    assert len(document["data_layer"]["databases"]) == 3
    tables = [
        t
        for d in document["data_layer"]["databases"]
        for s in d["schemas"]
        for t in s["tables"]
    ]
    assert len(tables) == 51
    columns = {c["id"] for t in tables for c in t["columns"]}
    assert len(document["data_layer"]["foreign_keys"]) == 80
    for fk in document["data_layer"]["foreign_keys"]:
        assert fk["source_column_id"] in columns and fk["target_column_id"] in columns
    concepts = document["semantic_layer"]["concepts"]
    assert len(concepts) == 9
    assert all(
        c in columns
        for concept in concepts
        for key in concept["keys"]
        for c in key["column_ids"]
    )
    assert not any(
        fk["use_in_join_paths"] for fk in document["semantic_layer"]["semantic_fks"]
    )


def test_without_ontology_really_removes_terms_from_cards(monkeypatch):
    class Journal:
        def record(self, **kwargs):
            pass

    service = SourceService(Settings(), load_catalog(), Journal())
    service._query = lambda *a, **k: {
        "rows": [[7298]],
        "columns": ["n"],
        "truncated": False,
    }
    monkeypatch.setenv("T2SQL_USE_ONTOLOGY", "0")
    assert service.get_table_card("paie", "payslips")["ontology_terms"] == []
    assert "Chiffre d'affaires" not in context("chiffre d'affaires", False)
    monkeypatch.setenv("T2SQL_USE_ONTOLOGY", "1")
    assert service.get_table_card("paie", "payslips")["ontology_terms"]


def test_import_reuses_discovered_catalog_ids_in_foreign_keys():
    draft = native_draft()
    discovered = native_draft()
    accounting = next(
        db for db in discovered["data_layer"]["databases"]
        if db["schemas"][0]["database_name"] == "compta"
    )
    table = next(t for t in accounting["schemas"][0]["tables"] if t["name"] == "ecriture")
    column = next(c for c in table["columns"] if c["name"] == "id_ecriture")
    original_id = column["id"]
    column["id"] = "discovered-column-id"
    remapped = auto_ontology._reuse_catalog_ids(draft, discovered)
    assert any(
        fk["target_column_id"] == "discovered-column-id"
        for fk in remapped["data_layer"]["foreign_keys"]
    )
    assert any(
        fk["target_column_id"] == original_id
        for fk in draft["data_layer"]["foreign_keys"]
    )


def test_nvidia_contract_import_compile_export_is_not_mislabelled_as_live(
    tmp_path, monkeypatch
):
    (tmp_path / "ontology").mkdir()
    for name in ["catalog.json", "business.yaml"]:
        (tmp_path / "ontology" / name).write_bytes(
            (auto_ontology.HERE / "ontology" / name).read_bytes()
        )
    monkeypatch.setattr(auto_ontology, "HERE", tmp_path)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "running": False,
                    "last_success_at": None
                    if len(calls) == 1
                    else "2026-11-19T12:00:00Z",
                },
            )
        if request.url.path.endswith("/export"):
            return httpx.Response(200, text=yaml.safe_dump(native_draft()))
        return httpx.Response(
            202 if request.url.path.endswith("/trigger") else 200,
            json={"success": True},
        )

    receipt = auto_ontology.generate(transport=httpx.MockTransport(handler))
    assert receipt["covered_tables"] == 51 and receipt["kind"] == "mock_contract_test"
    assert receipt["human_certification"] is False
    assert "/api/model/import" in calls and "/api/model/export" in calls


def test_nvidia_partial_export_cannot_create_generation_receipt(tmp_path, monkeypatch):
    (tmp_path / "ontology").mkdir()
    monkeypatch.setattr(auto_ontology, "HERE", tmp_path)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "running": False,
                    "last_success_at": None if len(seen) == 1 else "changed",
                },
            )
        if request.url.path.endswith("/export"):
            return httpx.Response(
                200, text=yaml.safe_dump({"data_layer": {"databases": []}})
            )
        return httpx.Response(200, json={"success": True})

    with pytest.raises(RuntimeError, match="incomplète"):
        auto_ontology.generate(transport=httpx.MockTransport(handler))
    assert not (tmp_path / "ontology/generation_receipt.json").exists()


def test_cpu_reranking_nim_contract():
    from fastapi.testclient import TestClient
    from text2sql.api import create_app

    client = TestClient(create_app(settings=Settings(api_key="test-only")))
    response = client.post(
        "/v1/reranking",
        headers={"Authorization": "Bearer test-only"},
        json={
            "model": "calorvia-cpu-lexical",
            "query": {"text": "facture client"},
            "passages": [{"text": "contrat travail"}, {"text": "facture client vente"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["rankings"][0]["index"] == 1
    assert response.json()["model"] == "calorvia-cpu-lexical"
