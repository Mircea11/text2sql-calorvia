"""Ontologie locale : brouillon métier et export natif NVIDIA traçable.

Un brouillon n'est jamais appelé « généré/certifié par NVIDIA ». Seul le flux
auto-ontology import/compilation/export peut produire cette preuve de provenance.
"""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path

import yaml

from .catalog import SENSITIVE
from .config import HERE


_RESTRICTED_FIELD = re.compile(
    r"(?<!\w)(?:" + "|".join(map(re.escape, sorted(SENSITIVE))) + r")(?!\w)",
    re.IGNORECASE,
)


def _verify_receipt(directory: Path) -> tuple[bytes, dict]:
    export = directory / "auto_ontology_export.yaml"
    receipt_path = directory / "generation_receipt.json"
    if not export.exists() or not receipt_path.exists():
        raise ValueError("Génération/export NVIDIA non vérifié ; brouillon insuffisant")
    content = export.read_bytes()
    receipt = json.loads(receipt_path.read_text())
    if (
        receipt.get("kind") != "live_nvidia_compilation_and_export"
        or receipt.get("export_sha256")
        != hashlib.sha256(content).hexdigest()
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
    return content, receipt


def _strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def prepare_agent_export(directory: Path) -> dict:
    """Crée une copie filtrée à partir d'un export natif vérifié."""
    content, receipt = _verify_receipt(directory)
    if "agent_projection" in receipt:
        raise ValueError("Utiliser l’archive de l’export brut NVIDIA")
    document = yaml.safe_load(content)
    data = document["data_layer"]
    semantic = document["semantic_layer"]
    restricted_columns = set()
    for database in data["databases"]:
        for schema in database["schemas"]:
            for table in schema["tables"]:
                columns = table["columns"]
                excluded = {c["id"] for c in columns if c["name"].casefold() in SENSITIVE}
                restricted_columns.update(excluded)
                table["columns"] = [c for c in columns if c["id"] not in excluded]
                table["pk"] = [column for column in table.get("pk", []) if column not in excluded]

    restricted_attributes = set()
    for term in semantic["terms"]:
        attrs = term["columns_attributes"]
        excluded = {a["id"] for a in attrs if a["column_id"] in restricted_columns}
        restricted_attributes.update(excluded)
        term["columns_attributes"] = [a for a in attrs if a["id"] not in excluded]
    data["foreign_keys"] = [
        edge for edge in data["foreign_keys"]
        if not restricted_columns.intersection(_strings(edge))
    ]
    removed_ids = restricted_columns | restricted_attributes
    semantic["semantic_fks"] = [
        edge for edge in semantic["semantic_fks"]
        if not removed_ids.intersection(_strings(edge))
    ]
    if removed_ids.intersection(_strings(document)):
        raise ValueError("Référence à un champ restreint dans une relation non filtrée")

    def scrub(value):
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items() if k != "sample_values"}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, str):
            return _RESTRICTED_FIELD.sub("[champ masqué]", value)
        return value

    projection = yaml.safe_dump(scrub(document), allow_unicode=True, sort_keys=False).encode()
    receipt["agent_projection"] = {
        "source_export_sha256": receipt["export_sha256"],
        "removed_columns": len(restricted_columns),
        "removed_attributes": len(restricted_attributes),
    }
    receipt["export_sha256"] = hashlib.sha256(projection).hexdigest()
    (HERE / "ontology/auto_ontology_export.yaml").write_bytes(projection)
    (HERE / "ontology/generation_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    )
    return receipt


def _verified_agent_export() -> tuple[dict, dict]:
    content, receipt = _verify_receipt(HERE / "ontology")
    document = yaml.safe_load(content)
    if "agent_projection" not in receipt or any(
        _RESTRICTED_FIELD.search(value) for value in _strings(document)
    ):
        raise ValueError("L’agent requiert un export NVIDIA filtré")
    return document, receipt


def verified_export() -> dict:
    """N'accepte que la copie filtrée et son reçu compatible avec les entrées."""
    _, receipt = _verified_agent_export()
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
        document, _ = _verified_agent_export()
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
