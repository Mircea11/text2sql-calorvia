"""Diagnostic sans modification : environnement réel et services déjà disponibles.

Ne démarre pas de service, ne charge pas de modèle, ne lit pas de ligne métier
et n'affiche jamais de DSN, clé ou mot de passe. Le résultat est partageable.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import shutil
import socket
import sys

import httpx
from packaging.requirements import Requirement

from .config import HERE, ROOT, Settings, local_url


def dependency_status() -> list[dict]:
    """Compare les contraintes Task 2 aux paquets de l'interpréteur actif."""
    result = []
    for line in (HERE / "requirements.in").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        try:
            installed = importlib.metadata.version(requirement.name)
            result.append(
                {
                    "package": requirement.name,
                    "installed": installed,
                    "compatible": requirement.specifier.contains(installed),
                }
            )
        except importlib.metadata.PackageNotFoundError:
            result.append(
                {"package": requirement.name, "installed": None, "compatible": False}
            )
    return result


def report() -> dict:
    """État des ports et du /models existant ; aucune requête de génération."""
    settings = Settings.load()
    checks = {}
    for name, port in {
        "erp": settings.erp_port,
        "compta": settings.compta_port,
        "paie": settings.paie_port,
        "journal_default": 5432,
    }.items():
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                checks[name] = {"port": port, "tcp_reachable": True}
        except OSError:
            checks[name] = {"port": port, "tcp_reachable": False}
    llm = {
        "configured": bool(settings.llm_url and settings.llm_model),
        "models_endpoint_ok": False,
        "generation_tested": False,
    }
    if llm["configured"]:
        try:
            url = local_url(settings.llm_url)
            with httpx.Client(
                timeout=3, trust_env=False, follow_redirects=False
            ) as client:
                response = client.get(
                    url + "/models",
                    headers={"Authorization": "Bearer " + settings.llm_key},
                )
                response.raise_for_status()
                llm["models_endpoint_ok"] = settings.llm_model in {
                    m["id"] for m in response.json()["data"]
                }
        except Exception as exc:
            llm["error_type"] = type(exc).__name__
    files = [
        "calorvia_tools.py",
        "calorvia_agent.py",
        "calorvia_mcp_server.py",
        "pyproject.toml",
    ]
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "dependencies": dependency_status(),
        "docker_available": bool(shutil.which("docker")),
        "services": checks,
        "llm": llm,
        "source_credentials_configured": bool(settings.source_password),
        "journal_configured": bool(settings.journal_dsn),
        "task1_file_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in files
            if (ROOT / name).exists()
        },
        "changes_made": False,
        "gpu_models_loaded": False,
    }
