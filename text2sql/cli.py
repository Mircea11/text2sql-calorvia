"""Commandes du laboratoire : préparation, vérification, API, ontologie et mesure."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import psycopg

from .config import HERE, ROOT, Settings


def preflight() -> dict:
    """Lit l'état local ; ne charge pas de modèle et ne lance pas d'expérience."""
    settings=Settings.load();checks={}
    packages=["sqlglot","psycopg","pymssql","langgraph","langchain-openai","fastapi","mcp"]
    checks["packages"]={p:importlib.metadata.version(p) for p in packages}
    checks["docker_available"]=bool(shutil.which("docker"))
    checks["source_password_configured"]=bool(settings.source_password)
    checks["journal_transport"]="dsn" if settings.journal_dsn else "existing Docker container helpdesk-ops-postgres-1"
    checks["api_key_configured"]=bool(settings.api_key)
    try:
        settings.require_llm()
        with httpx.Client(timeout=5,trust_env=False,follow_redirects=False) as client:
            response=client.get(settings.llm_url.rstrip("/")+"/models",headers={"Authorization":"Bearer "+settings.llm_key});response.raise_for_status()
            identifiers=[m["id"] for m in response.json().get("data",[])]
            checks["shared_llm_model_found"]=settings.llm_model in identifiers
    except Exception as exc:checks["shared_llm_error"]=type(exc).__name__
    checks["sources_executed"]=False
    return checks


def dependency_audit(install: bool=False) -> dict:
    """Préserve toutes les versions déjà installées ; n'effectue aucun uv sync."""
    from packaging.requirements import Requirement
    missing=[];incompatible=[]
    for line in (HERE/"requirements.in").read_text().splitlines():
        if not line.strip() or line.startswith("#"):continue
        requirement=Requirement(line)
        try:version=importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:missing.append(line);continue
        if version not in requirement.specifier:incompatible.append({"package":requirement.name,"installed":version,"required":str(requirement.specifier)})
    if install:
        if incompatible:raise RuntimeError("Conflit de dépendances détecté ; environnement existant préservé: "+json.dumps(incompatible))
        if missing:
            target=ROOT/"data"/"text2sql";target.mkdir(parents=True,exist_ok=True)
            constraints=target/"existing-versions.txt"
            constraints.write_text("\n".join(f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions())+"\n")
            subprocess.run(["uv","pip","install","--python",sys.executable,"--constraint",str(constraints),*missing],check=True)
    return {"missing":missing,"incompatible":incompatible,"existing_versions_preserved":True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["dependencies","preflight","init-journal","verify-sources","serve","ask","offline-build","offline-check","ontology-draft","ontology-prepare","ontology-start","ontology-generate","ontology-stop","evaluate"])
    parser.add_argument("--install",action="store_true")
    parser.add_argument("--question",default="")
    parser.add_argument("--sources",type=Path,default=ROOT/"data/text2sql/sources_calorvia/sql")
    parser.add_argument("--without-ontology",action="store_true")
    parser.add_argument("--limit",type=int)
    parser.add_argument("--allow-inference",action="store_true",help="Confirme qu'un créneau de calcul est libre pour les appels au modèle existant")
    args=parser.parse_args();settings=Settings.load()
    if args.command=="dependencies":print(json.dumps(dependency_audit(args.install),indent=2))
    elif args.command=="preflight":print(json.dumps(preflight(),indent=2))
    elif args.command=="init-journal":
        from .journal import Journal
        Journal(settings.journal_dsn).initialize()
        print("Schéma text2sql_journal initialisé ; schémas RAG et sources préservés")
    elif args.command=="verify-sources":
        from .catalog import load_catalog
        from .sources import SourceService
        service=SourceService(settings,load_catalog())
        for source,table,count in [("erp","VTE_FACT",10185),("compta","ecriture",20562),("paie","payslips",7298)]:
            data=service.execute_sql(source,f"SELECT COUNT(*) AS nombre FROM {table}")
            if not data.get("valid") or int(data["rows"][0][0])!=count:raise RuntimeError(f"Source {source} incorrecte ou inaccessible")
            print(f"{source}: compte agent_ro et volume de référence vérifiés")
    elif args.command=="serve":
        import uvicorn
        uvicorn.run("text2sql.api:app",host="127.0.0.1",port=9000,workers=1)
    elif args.command=="ask":
        from .agent import answer
        print(asyncio.run(answer(args.question,use_ontology=not args.without_ontology))["answer"])
    elif args.command=="offline-build":
        from .offline import build_offline
        build_offline(args.sources,ROOT/"data/text2sql/offline")
    elif args.command=="offline-check":
        from .evaluation import verify_references
        print(json.dumps(verify_references(ROOT/"data/text2sql/offline"),ensure_ascii=False,indent=2))
    elif args.command=="ontology-draft":
        from .auto_ontology import write_draft
        write_draft();print("Brouillon natif écrit ; aucune génération NVIDIA ni certification humaine revendiquée")
    elif args.command=="ontology-prepare":
        from .runtime import prepare_runtime
        print(prepare_runtime(settings))
    elif args.command=="ontology-start":
        if not args.allow_inference:raise RuntimeError("Prévoir un créneau libre ; les ordonnanceurs NVIDIA peuvent appeler les modèles au démarrage")
        from .runtime import start_runtime
        start_runtime()
    elif args.command=="ontology-generate":
        if not args.allow_inference:raise RuntimeError("Prévoir un créneau libre avant la génération")
        from .auto_ontology import generate
        print(json.dumps(generate(),indent=2))
    elif args.command=="ontology-stop":
        from .runtime import stop_runtime
        stop_runtime()
    elif args.command=="evaluate":
        if not args.allow_inference:raise RuntimeError("Prévoir un créneau libre avant l'évaluation séquentielle")
        from .evaluation import evaluate_live
        print(asyncio.run(evaluate_live(not args.without_ontology,limit=args.limit)))


if __name__=="__main__":main()
