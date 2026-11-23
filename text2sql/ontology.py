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


def _keywords(text: str) -> set[str]:
    return {word for word in re.findall(r"[^\W\d_]+", text.casefold()) if len(word) >= 4}


def table_terms(source: str, table: str) -> list[dict]:
    qualified = f"{source}.{table}".casefold()
    return [
        {key: term[key] for key in ("name", "definition", "calculation", "time") if key in term}
        for term in business_rules()["terms"]
        if qualified in {name.casefold() for name in term["tables"]}
    ]


def context(question: str, enabled: bool) -> str:
    if not enabled:
        return "Ontologie désactivée pour l'expérience de référence. Les fiches de tables restent disponibles."
    rules = business_rules()
    export = HERE / "ontology" / "auto_ontology_export.yaml"
    words = _keywords(question)
    ranked = sorted(
        rules["terms"],
        key=lambda term: len(words & _keywords(
            " ".join([term["name"], *term["synonyms"], *term["tables"]])
        )),
        reverse=True,
    )
    payload = {
        "cross_source_links": rules["cross_source_links"],
        "terms": [
            {key: value for key, value in term.items() if key != "synonyms"}
            for term in ranked[:4]
        ],
        "provenance": "brouillon métier révisé par IA ; certification humaine en attente",
    }
    if export.exists():
        document, receipt = _verified_agent_export()
        semantic = document.get("semantic_layer", {})
        # Les UUID et les fiches de colonnes restent dans le catalogue MCP.
        def summaries(items):
            matches = []
            for item in items:
                name = item.get("name") or ""
                description = item.get("description") or ""
                score = len(words & _keywords(name + " " + description))
                if score:
                    matches.append((score, {"name": name[:100], "description": description[:300]}))
            return [item for _, item in sorted(matches, key=lambda match: -match[0])[:3]]

        payload["auto_ontology_terms"] = summaries(semantic.get("terms", []))
        payload["auto_ontology_calculations"] = summaries(
            semantic.get("sql_attributes", {}).get("manual", [])
        )
        if receipt.get("business_review", {}).get("status") == "approved":
            payload["provenance"] = "Définitions et liens métier approuvés pour cet instantané."
        else:
            payload["provenance"] = "Copie filtrée NVIDIA ; définitions métier à réviser."
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
