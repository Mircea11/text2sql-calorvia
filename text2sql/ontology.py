"""Ontologie locale : brouillon métier et export natif NVIDIA traçable.

Un brouillon n'est jamais appelé « généré/certifié par NVIDIA ». Seul le flux
auto-ontology import/compilation/export peut produire cette preuve de provenance.
"""

from __future__ import annotations

import json
import hashlib

import yaml

from .config import HERE


def verified_export() -> dict:
    """Vérifie la provenance du YAML ; refuse un reçu périmé ou un simple brouillon."""
    export = HERE / "ontology/auto_ontology_export.yaml"
    receipt_path = HERE / "ontology/generation_receipt.json"
    if not export.exists() or not receipt_path.exists():
        raise ValueError("Génération/export NVIDIA non vérifié ; brouillon insuffisant")
    receipt = json.loads(receipt_path.read_text())
    if (
        receipt.get("kind") != "live_nvidia_compilation_and_export"
        or receipt.get("export_sha256")
        != hashlib.sha256(export.read_bytes()).hexdigest()
    ):
        raise ValueError("Reçu NVIDIA invalide ou export modifié")
    for name in ["catalog.json", "business.yaml"]:
        if (
            receipt.get("input_sha256", {}).get(name)
            != hashlib.sha256((HERE / "ontology" / name).read_bytes()).hexdigest()
        ):
            raise ValueError(
                "Ontologie périmée : entrées modifiées depuis la génération"
            )
    return receipt


def business_rules() -> dict:
    return yaml.safe_load((HERE / "ontology" / "business.yaml").read_text())


def relevant_terms(question: str) -> list[dict]:
    terms = business_rules()["terms"]
    words = set(question.casefold().split())
    ranked = sorted(
        terms,
        key=lambda t: sum(
            w
            in (
                t["name"]
                + " "
                + " ".join(t.get("tables", []))
                + " "
                + " ".join(t.get("synonyms", []))
            ).casefold()
            for w in words
        ),
        reverse=True,
    )
    return ranked[:8]


def context(question: str, enabled: bool) -> str:
    if not enabled:
        return "Ontologie désactivée pour l'expérience de référence. Les fiches de tables restent disponibles."
    rules = business_rules()
    export = HERE / "ontology" / "auto_ontology_export.yaml"
    payload = {
        "cross_source_links": rules["cross_source_links"],
        "terms": relevant_terms(question),
        "provenance": "brouillon métier révisé par IA ; certification humaine en attente",
    }
    if export.exists():
        document = yaml.safe_load(export.read_text())
        semantic = document.get("semantic_layer", {})
        words = set(question.casefold().split())

        def score(t):
            return sum(w in json.dumps(t, ensure_ascii=False).casefold() for w in words)

        payload["auto_ontology_terms"] = sorted(
            semantic.get("terms", []), key=score, reverse=True
        )[:8]
        payload["auto_ontology_calculations"] = sorted(
            semantic.get("sql_attributes", {}).get("manual", []),
            key=score,
            reverse=True,
        )[:5]
        payload["provenance"] = (
            "export natif NVIDIA présent ; consulter la preuve de génération et le registre de certification"
        )
    return json.dumps(payload, ensure_ascii=False)
