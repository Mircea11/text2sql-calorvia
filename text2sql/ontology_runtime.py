"""Prépare NVIDIA dans des conteneurs CPU, sans changer l'environnement du RAG.

NVIDIA impose notamment openai==2.44.0 et langchain-openai<1.3.5 ; le banc de
vérification utilise openai 3.55.1/langchain-openai 1.8.3. Cette dépendance est
donc isolée, tandis que les serveurs de modèles et les sources restent partagés.
"""

from __future__ import annotations

import ast
import json
import os
import secrets
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import quote

import yaml

from .auto_ontology import NVIDIA_COMMIT
from .config import ROOT, Settings, local_url

RUNTIME = ROOT / "data" / "text2sql" / "ontology-runtime"


def prepare_runtime(settings: Settings | None = None) -> Path:
    """Prépare une configuration privée, épingle le code officiel ; ne lance rien."""
    settings = settings or Settings.load()
    settings.require_llm()
    if not settings.source_password or not settings.api_key:
        raise ValueError(
            "Configurer le mot de passe agent_ro et la clé de l'API Text-to-SQL avant NVIDIA"
        )
    embed = {}
    for node in ast.parse((ROOT / "calorvia_tools.py").read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    embed[target.id] = node.value.value
    embed_url = os.getenv(
        "T2SQL_EMBED_URL", str(embed.get("EMBEDDING_URL", ""))
    ).removesuffix("/embeddings")
    embed_model = os.getenv("T2SQL_EMBED_MODEL", str(embed.get("EMBEDDING_MODEL", "")))
    local_url(embed_url)
    if not embed_model:
        raise ValueError("Modèle d'embeddings existant non identifié")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    source = RUNTIME / "upstream"
    if not source.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/NVIDIA/auto-ontology.git",
                str(source),
            ],
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "--detach", NVIDIA_COMMIT], cwd=source, check=True
        )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if revision != NVIDIA_COMMIT:
        raise RuntimeError("Code NVIDIA différent du commit vérifié ; dossier préservé")
    envfile = RUNTIME / "runtime.env"
    if envfile.exists():
        from dotenv import dotenv_values

        old = dotenv_values(envfile)
        password = old.get("POSTGRES_PASSWORD") or secrets.token_urlsafe(32)
    else:
        password = secrets.token_urlsafe(32)
    values = {
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5435",
        "POSTGRES_USER": "ontology",
        "POSTGRES_PASSWORD": password,
        "POSTGRES_DATABASE": "auto_ontology",
        "INGESTION_SERVICE_URL": "http://127.0.0.1:3002",
        "INGESTION_PORT": "3002",
        "LLM_MAX_INFLIGHT": "1",
        "SEMANTIC_LLM_MAX_INFLIGHT": "1",
        "INGEST_INTERVAL_HOURS": "87600",
        "KUMO_RFM_API_KEY": "",
        "KUMO_RFM_API_URL": "",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "DO_NOT_TRACK": "1",
    }
    for role in ["DEFAULT_MODELS", "REASONING", "NON_REASONING"]:
        values.update(
            {
                role + "_ENDPOINT": settings.llm_url,
                role + "_MODEL": settings.llm_model,
                role + "_API_KEY": settings.llm_key,
            }
        )
    values.update(
        {
            "EMBED_ENDPOINT": embed_url,
            "EMBED_MODEL": embed_model,
            "EMBED_API_KEY": os.getenv("T2SQL_EMBED_KEY", "local"),
            "RERANK_ENDPOINT": "http://127.0.0.1:9000/v1/reranking",
            "RERANK_MODEL": "calorvia-cpu-lexical",
            "RERANK_API_KEY": settings.api_key,
        }
    )
    values["CONNECTION_STRINGS"] = ",".join(
        f"postgresql://agent_ro:{quote(settings.source_password, safe='')}@127.0.0.1:{port}/{db}"
        for db, port in [("compta", settings.compta_port), ("paie", settings.paie_port)]
    )
    # Les comptes des sources restent agent_ro ; le PostgreSQL d'ontologie est
    # séparé, car les migrations NVIDIA possèdent leur schéma public.
    envfile.write_text(
        "\n".join(k + "=" + json.dumps(v) for k, v in values.items()) + "\n"
    )
    envfile.chmod(0o600)
    common = {
        "image": "calorvia-auto-ontology:" + NVIDIA_COMMIT[:12],
        "build": {"context": str(source)},
        "network_mode": "host",
        "env_file": [str(envfile)],
        "restart": "no",
    }
    compose = {
        "name": "calorvia-text2sql-ontology",
        "services": {
            "ontology-db": {
                "image": "pgvector/pgvector:pg17",
                "network_mode": "host",
                "environment": {
                    "POSTGRES_USER": "ontology",
                    "POSTGRES_PASSWORD": password,
                    "POSTGRES_DB": "auto_ontology",
                    "PGPORT": "5435",
                },
                "command": [
                    "postgres",
                    "-p",
                    "5435",
                    "-c",
                    "listen_addresses=127.0.0.1",
                ],
                "volumes": ["ontology-data:/var/lib/postgresql/data"],
                "healthcheck": {
                    "test": [
                        "CMD",
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-p",
                        "5435",
                        "-U",
                        "ontology",
                    ],
                    "interval": "5s",
                    "timeout": "5s",
                    "retries": 20,
                },
            },
            "migrate": {
                **common,
                "command": ["migrate"],
                "depends_on": {"ontology-db": {"condition": "service_healthy"}},
            },
            "backend": {
                **common,
                "entrypoint": [
                    "python",
                    "-m",
                    "uvicorn",
                    "auto_ontology.server.__main__:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "3001",
                ],
                "depends_on": {
                    "migrate": {"condition": "service_completed_successfully"}
                },
            },
            "ingestion": {
                **common,
                "entrypoint": [
                    "python",
                    "-m",
                    "uvicorn",
                    "auto_ontology.ingestion_service.__main__:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "3002",
                ],
                "depends_on": {
                    "migrate": {"condition": "service_completed_successfully"}
                },
            },
        },
        "volumes": {"ontology-data": {}},
    }
    path = RUNTIME / "compose.yaml"
    path.write_text(yaml.safe_dump(compose, sort_keys=False))
    path.chmod(0o600)
    return path


def start_runtime() -> None:
    if not shutil.which("docker"):
        raise RuntimeError("Docker absent ; aucune modification des services existants")
    path = RUNTIME / "compose.yaml"
    if not path.exists():
        raise RuntimeError("Exécuter ontology-prepare")
    for port in [5435, 3001, 3002]:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(
                    f"Port {port} occupé ; réutiliser/vérifier le service existant au lieu de le remplacer"
                )
    subprocess.run(
        ["docker", "compose", "-f", str(path), "up", "-d", "--build"], check=True
    )


def stop_runtime() -> None:
    """Arrête uniquement ce projet CPU ; préserve les volumes et tous les modèles."""
    subprocess.run(
        ["docker", "compose", "-f", str(RUNTIME / "compose.yaml"), "stop"], check=True
    )
