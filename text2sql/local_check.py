"""Diagnostic local sans installation, sans inférence et sans affichage de secrets.

Lancer avec le Python de l'environnement RAG depuis la racine du dépôt.
Écrit data/text2sql/local_environment.json pour poursuivre la préparation.
"""

from __future__ import annotations

import http.client
import importlib.metadata
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def main():
    root = Path(__file__).resolve().parents[1]
    try:
        from dotenv import dotenv_values

        values = {
            **dotenv_values(root / ".env"),
            **dotenv_values(root / "text2sql/.env"),
            **os.environ,
        }
    except ImportError:
        values = dict(os.environ)
        for p in [root / ".env", root / "text2sql/.env"]:
            if p.exists():
                for line in p.read_text().splitlines():
                    if "=" in line and not line.lstrip().startswith("#"):
                        k, v = line.split("=", 1)
                        values.setdefault(k.strip(), v.strip().strip("\"'"))
    report = {
        "kind": "read_only_local_environment_diagnostic",
        "at": datetime.now(timezone.utc).isoformat(),
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "packages": {},
        "ports": {},
        "docker": bool(shutil.which("docker")),
        "gpu_inference_started": False,
        "services_changed": False,
    }
    for package in [
        "docling",
        "langchain",
        "langchain-openai",
        "langgraph",
        "mcp",
        "psycopg",
        "pymssql",
        "sqlglot",
        "fastapi",
        "httpx",
        "pytest",
        "duckdb",
    ]:
        try:
            report["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["packages"][package] = None
    for port in [
        1433,
        14330,
        5432,
        5433,
        5434,
        5435,
        8000,
        8001,
        8002,
        9000,
        3001,
        3002,
    ]:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                report["ports"][str(port)] = True
        except OSError:
            report["ports"][str(port)] = False
    candidates = [
        root / "data/text2sql/sources_calorvia",
        root / "sources_calorvia",
        root.parent / "sources_calorvia",
        root.parent / "calorvia_t2sql/sources_calorvia",
    ]
    report["source_directories"] = [
        str(p) for p in candidates if (p / "sql/01_erp_gespro_sqlserver.sql").exists()
    ]
    report["configuration_present"] = {
        key: bool(values.get(key))
        for key in [
            "CALORVIA_LLM_BASE_URL",
            "CALORVIA_LLM_MODEL",
            "T2SQL_LLM_URL",
            "T2SQL_LLM_MODEL",
            "AGENT_RO_PASSWORD",
            "T2SQL_SOURCE_PASSWORD",
            "T2SQL_JOURNAL_DSN",
            "T2SQL_API_KEY",
        ]
    }
    url = values.get("T2SQL_LLM_URL") or values.get("CALORVIA_LLM_BASE_URL")
    if url:
        parsed = urlsplit(url)
        if (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and not parsed.username
            and not parsed.query
        ):
            try:
                client = http.client.HTTPConnection(
                    parsed.hostname, parsed.port or 80, timeout=3
                )
                key = (
                    values.get("T2SQL_LLM_KEY")
                    or values.get("CALORVIA_LLM_API_KEY")
                    or "local"
                )
                client.request(
                    "GET",
                    parsed.path.rstrip("/") + "/models",
                    headers={"Authorization": "Bearer " + key},
                )
                response = client.getresponse()
                report["llm_models_http_status"] = response.status
                if response.status == 200:
                    report["local_llm_models"] = [
                        m["id"]
                        for m in json.loads(response.read(100000)).get("data", [])
                    ]
                client.close()
            except Exception as exc:
                report["local_llm_error"] = type(exc).__name__
        else:
            report["local_llm_error"] = "Non-local or invalid URL; not contacted"
    if shutil.which("nvidia-smi"):
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            report["gpu_memory"] = result.stdout.strip().splitlines()
    if report["docker"]:
        command = [
            "docker",
            "inspect",
            "--format",
            "{{.Name}} {{.State.Status}} {{json .NetworkSettings.Ports}}",
            "helpdesk-ops-postgres-1",
            "calorvia-erp",
            "calorvia-compta",
            "calorvia-paie",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        report["relevant_containers"] = result.stdout.strip().splitlines()
    target = root / "data/text2sql/local_environment.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Diagnostic sauvegardé :", target)
    print("Aucune installation, aucune inférence GPU, aucun service modifié.")
    print(
        "Le rapport contient les versions et la disponibilité des services ; aucun mot de passe ni clé API."
    )


if __name__ == "__main__":
    main()
