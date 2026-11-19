"""Commandes du laboratoire : préparation, vérification, API, ontologie et mesure."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

from .config import HERE, ROOT, Settings


def preflight() -> dict:
    """Diagnostic complet sans installation ni génération de modèle."""
    from .preflight import report
    return report()


def dependency_audit(install: bool = False) -> dict:
    """Préserve toutes les versions déjà installées ; n'effectue aucun uv sync."""
    from packaging.requirements import Requirement

    missing = []
    incompatible = []
    for line in (HERE / "requirements.in").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        try:
            version = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(line)
            continue
        if version not in requirement.specifier:
            incompatible.append(
                {
                    "package": requirement.name,
                    "installed": version,
                    "required": str(requirement.specifier),
                }
            )
    if install:
        if incompatible:
            raise RuntimeError(
                "Conflit de dépendances détecté ; environnement existant préservé: "
                + json.dumps(incompatible)
            )
        if missing:
            target = ROOT / "data" / "text2sql"
            target.mkdir(parents=True, exist_ok=True)
            constraints = target / "existing-versions.txt"
            constraints.write_text(
                "\n".join(
                    f"{d.metadata['Name']}=={d.version}"
                    for d in importlib.metadata.distributions()
                )
                + "\n"
            )
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    sys.executable,
                    "--constraint",
                    str(constraints),
                    *missing,
                ],
                check=True,
            )
    return {
        "missing": missing,
        "incompatible": incompatible,
        "existing_versions_preserved": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "dependencies",
            "preflight",
            "init-journal",
            "verify-sources",
            "serve",
            "ask",
            "offline-build",
            "offline-check",
            "ontology-draft",
            "ontology-prepare",
            "ontology-start",
            "ontology-generate",
            "ontology-stop",
            "evaluate",
            "native-check",
            "compare",
        ],
    )
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--question", default="")
    parser.add_argument(
        "--sources", type=Path, default=ROOT / "data/text2sql/sources_calorvia/sql"
    )
    parser.add_argument("--without-ontology", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--without-run", type=Path)
    parser.add_argument("--with-run", type=Path)
    parser.add_argument(
        "--allow-inference",
        action="store_true",
        help="Confirme qu'un créneau de calcul est libre pour les appels au modèle existant",
    )
    args = parser.parse_args()
    settings = Settings.load()
    if args.command == "dependencies":
        print(json.dumps(dependency_audit(args.install), indent=2))
    elif args.command == "preflight":
        print(json.dumps(preflight(), indent=2))
    elif args.command == "init-journal":
        from .journal import Journal

        Journal(settings.journal_dsn).initialize()
        print("Schéma text2sql_journal initialisé ; schémas RAG et sources préservés")
    elif args.command == "verify-sources":
        from .catalog import load_catalog
        from .sources import SourceService

        service = SourceService(settings, load_catalog())
        for source, table, count in [
            ("erp", "VTE_FACT", 10185),
            ("compta", "ecriture", 20562),
            ("paie", "payslips", 7298),
        ]:
            data = service.execute_sql(
                source, f"SELECT COUNT(*) AS nombre FROM {table}"
            )
            if not data.get("valid") or int(data["rows"][0][0]) != count:
                raise RuntimeError(f"Source {source} incorrecte ou inaccessible")
            print(f"{source}: compte agent_ro et volume de référence vérifiés")
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("text2sql.api:app", host="127.0.0.1", port=9000, workers=1)
    elif args.command == "ask":
        from .agent import answer

        print(
            asyncio.run(answer(args.question, use_ontology=not args.without_ontology))[
                "answer"
            ]
        )
    elif args.command == "offline-build":
        from .offline import build_offline

        build_offline(args.sources, ROOT / "data/text2sql/offline")
    elif args.command == "offline-check":
        from .evaluation import verify_references
        from .offline import verify_manifest
        verify_manifest(args.sources, ROOT / "data/text2sql/offline")

        print(
            json.dumps(
                verify_references(ROOT / "data/text2sql/offline"),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "ontology-draft":
        from .auto_ontology import write_draft

        write_draft()
        print(
            "Brouillon natif écrit ; aucune génération NVIDIA ni certification humaine revendiquée"
        )
    elif args.command == "ontology-prepare":
        from .ontology_runtime import prepare_runtime

        print(prepare_runtime(settings))
    elif args.command == "ontology-start":
        if not args.allow_inference:
            raise RuntimeError(
                "Prévoir un créneau libre ; les ordonnanceurs NVIDIA peuvent appeler les modèles au démarrage"
            )
        from .ontology_runtime import start_runtime

        start_runtime()
    elif args.command == "ontology-generate":
        if not args.allow_inference:
            raise RuntimeError("Prévoir un créneau libre avant la génération")
        from .auto_ontology import generate

        print(json.dumps(generate(), indent=2))
    elif args.command == "ontology-stop":
        from .ontology_runtime import stop_runtime

        stop_runtime()
    elif args.command == "evaluate":
        if not args.allow_inference:
            raise RuntimeError(
                "Prévoir un créneau libre avant l'évaluation séquentielle"
            )
        from .evaluation import evaluate_live

        if args.limit is not None:
            raise RuntimeError(
                "Les campagnes officielles couvrent les 44 questions ; --limit n'est pas utilisé"
            )
        print(asyncio.run(evaluate_live(not args.without_ontology, resume=args.resume)))
    elif args.command == "native-check":
        from .evaluation import verify_native_references

        print(json.dumps(verify_native_references(), ensure_ascii=False, indent=2))
    elif args.command == "compare":
        from .evaluation import compare_runs

        if args.without_run is None or args.with_run is None:
            raise ValueError("Fournir --without-run et --with-run")
        print(
            json.dumps(
                compare_runs(args.without_run, args.with_run),
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
