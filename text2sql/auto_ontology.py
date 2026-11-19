"""Pont vérifiable vers NVIDIA Auto Ontology (commit documenté, API locale).

Produit un brouillon natif à partir des 51 DDL, importe sans effacer le catalogue,
déclenche la compilation, attend sa réussite et exporte le YAML NVIDIA. Aucune
preuve de génération n'est écrite si un appel échoue ou si la couverture manque.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
import yaml

from .catalog import SENSITIVE, load_catalog
from .config import HERE, local_url
from .ontology import business_rules

NVIDIA_COMMIT = "ee42eff638ebd136c1c4fe4ab290785f912bb4bc"


def stable_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL,"calorvia-text2sql/"+name))


def native_draft(catalog=None) -> dict:
    """Format natif NVIDIA ; les descriptions ERP sont un import explicite, pas un connecteur SQL Server fictif."""
    catalog=catalog or load_catalog()
    databases, foreign_keys, terms=[], [], []
    rules=business_rules()["terms"]
    for source,data in catalog["sources"].items():
        tables=[]
        for name,table in data["tables"].items():
            tid=stable_id(f"{source}.{name}")
            columns=[]; attributes=[]
            description=table["description"] or f"Table source {source}.{name} ; définition à réviser."
            related=[r for r in rules if f"{source}.{name}" in r.get("tables",[])]
            description+=" "+" ".join(r["definition"] for r in related)
            for col,value in table["columns"].items():
                # Ne jamais importer les attributs interdits dans la couche sémantique.
                if col.casefold() in SENSITIVE: continue
                cid=stable_id(f"{source}.{name}.{col}")
                columns.append({"id":cid,"name":col,"type":value["type"],"description":value["description"],"is_unique":col in table["primary_key"]})
                attributes.append({"id":stable_id("attr."+f"{source}.{name}.{col}"),"name":col,"description":value["description"],"column_id":cid})
            tables.append({"id":tid,"name":name,"description":description,"pk":[stable_id(f"{source}.{name}.{c}") for c in table["primary_key"] if c.casefold() not in SENSITIVE],"type":"table","columns":columns})
            terms.append({"id":stable_id("term."+f"{source}.{name}"),"name":f"{source}.{name}","description":description,"represents":[tid],"columns_attributes":attributes})
            for fk in table["foreign_keys"]:
                for left,right in zip(fk["columns"],fk["target_columns"]):
                    foreign_keys.append({"source_column_id":stable_id(f"{source}.{name}.{left}"),"target_column_id":stable_id(f"{source}.{fk['target_table']}.{right}")})
        databases.append({"id":stable_id(source),"dialect":data["dialect"],"schemas":[{"id":stable_id(source+".schema"),"name":data["schema"],"database_name":data["database"],"tables":tables}]})
    return {"data_layer":{"databases":databases,"foreign_keys":foreign_keys,"joins":[]},"semantic_layer":{"terms":terms,"concepts":[],"semantic_fks":[],"sql_attributes":{"manual":[],"table":[],"sql":[],"bridge_table":[]},"custom_analyses":[]},"zones":[]}


def write_draft() -> None:
    target=HERE/"ontology"/"native_draft.yaml"
    target.write_text(yaml.safe_dump(native_draft(),allow_unicode=True,sort_keys=False))


def generate(*, timeout_s=3600, transport=None) -> dict:
    """Compile/exporte réellement ; l'appelant planifie cette charge sur un créneau libre."""
    url=local_url(os.getenv("T2SQL_AUTO_ONTOLOGY_URL","http://127.0.0.1:3001"))
    headers={"x-api-key":os.getenv("T2SQL_AUTO_ONTOLOGY_TOKEN","")}
    with httpx.Client(base_url=url,headers=headers,timeout=120,follow_redirects=False,trust_env=False,transport=transport) as client:
        before=client.get("/api/semantic-compilation/status");before.raise_for_status()
        previous=before.json().get("last_success_at")
        yaml_text=yaml.safe_dump(native_draft(),allow_unicode=True,sort_keys=False)
        imported=client.post("/api/model/import",params={"replace":"false","embed":"true"},content=yaml_text.encode(),headers={"Content-Type":"application/x-yaml"});imported.raise_for_status()
        trigger=client.post("/api/semantic-compilation/trigger");trigger.raise_for_status()
        start=time.monotonic()
        while True:
            response=client.get("/api/semantic-compilation/status");response.raise_for_status();status=response.json()
            if status.get("last_success_at") and status.get("last_success_at")!=previous and not status.get("running"):
                break
            if status.get("last_failure_at") and status.get("last_failure_at")!=before.json().get("last_failure_at"):
                raise RuntimeError("Compilation NVIDIA en échec ; aucun résultat certifié produit")
            if time.monotonic()-start>timeout_s:
                raise TimeoutError("Compilation NVIDIA non terminée ; reprise locale nécessaire")
            time.sleep(3)
        export=client.post("/api/model/export",json={"databases":[],"format":"auto_ontology","include_ontology":False});export.raise_for_status()
        document=yaml.safe_load(export.text)
        exported={(s["database_name"],t["name"].casefold()) for d in document["data_layer"]["databases"] for s in d["schemas"] for t in s["tables"]}
        expected={(d["database"],t.casefold()) for d in load_catalog()["sources"].values() for t in d["tables"]}
        if not expected<=exported:
            raise RuntimeError(f"Couverture NVIDIA incomplète : {len(expected-exported)} tables manquantes")
        target=HERE/"ontology"/"auto_ontology_export.yaml"
        target.write_text(export.text)
        receipt={"kind":"live_nvidia_compilation_and_export","upstream_commit":NVIDIA_COMMIT,"generated_at":datetime.now(timezone.utc).isoformat(),"compilation_status":status,"covered_tables":len(expected),"export_sha256":hashlib.sha256(export.content).hexdigest(),"human_certification":False}
        (HERE/"ontology"/"generation_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
        return receipt
