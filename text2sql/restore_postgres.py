"""Démarre une seule source PostgreSQL du Compose fourni et contrôle sa restauration.

Lancer avec le Python partagé, le dossier docker officiel et le nom compta ou paie.
La configuration privée reste dans ce dossier. Le contrôle utilise agent_ro sur
le port TCP local. Les ACL d'écriture font l'objet d'un test indépendant.
"""

import argparse
import os
import secrets
import subprocess
import time
from pathlib import Path

import psycopg
from dotenv import dotenv_values

SOURCES = {
    "compta": (5433, "ecriture", 20562),
    "paie": (5434, "payslips", 7298),
}

LOOPBACK = """services:
  erp-sqlserver:
    ports: !override ["127.0.0.1:14330:1433"]
  compta-postgres:
    ports: !override ["127.0.0.1:5433:5432"]
  paie-postgres:
    ports: !override ["127.0.0.1:5434:5432"]
"""


def credentials(folder):
    """Crée le .env au premier lancement et conserve les secrets lors d'une reprise."""
    path = folder / ".env"
    if not path.exists():
        settings = {
            "PG_ADMIN_USER": "calorvia",
            "PG_ADMIN_PASSWORD": secrets.token_hex(24),
            "MSSQL_SA_PASSWORD": "Aa1" + secrets.token_hex(24),
            "AGENT_RO_PASSWORD": secrets.token_hex(24),
            "FORCE_RESTORE": "0",
        }
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            for key, value in settings.items():
                print(f"{key}={value}", file=out)
    values = dotenv_values(path, interpolate=False)
    if not all(
        values.get(k)
        for k in (
            "PG_ADMIN_USER",
            "PG_ADMIN_PASSWORD",
            "MSSQL_SA_PASSWORD",
            "AGENT_RO_PASSWORD",
        )
    ):
        raise SystemExit("Configuration .env incomplète, fichier conservé.")
    return values


def restore(folder, source):
    """Démarre le service choisi puis vérifie identité, lecture seule et volume."""
    folder = folder.resolve()
    if not (folder / "docker-compose.yml").is_file():
        raise SystemExit("docker-compose.yml absent du dossier fourni.")
    endpoint = os.environ.get("DOCKER_HOST")
    if not endpoint or os.environ.get("DOCKER_CONTEXT"):
        endpoint = subprocess.check_output(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            text=True,
        ).strip()
    if not endpoint.startswith("unix://"):
        raise SystemExit("Le contexte Docker doit viser le socket local du Z4.")
    values = credentials(folder)
    service = source + "-postgres"
    port, table, expected = SOURCES[source]
    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            "calorvia-sources",
            "--env-file",
            ".env",
            "-f",
            "docker-compose.yml",
            "-f",
            "-",
            "up",
            "-d",
            "--no-deps",
            "--no-recreate",
            "--wait",
            service,
        ],
        cwd=folder,
        env={
            **os.environ,
            **{
                k: values[k]
                for k in (
                    "PG_ADMIN_USER",
                    "PG_ADMIN_PASSWORD",
                    "MSSQL_SA_PASSWORD",
                    "AGENT_RO_PASSWORD",
                )
            },
            "FORCE_RESTORE": "0",
        },
        input=LOOPBACK,
        text=True,
        check=True,
    )
    # Le contrôle de santé peut répondre pendant l'initialisation du volume.
    deadline = time.monotonic() + 180
    while True:
        try:
            with psycopg.connect(
                host="127.0.0.1",
                port=port,
                dbname=source,
                user="agent_ro",
                password=values["AGENT_RO_PASSWORD"],
                connect_timeout=3,
            ) as conn:
                role, readonly, count = conn.execute(
                    "SELECT current_user, current_setting('transaction_read_only'), "
                    f"COUNT(*) FROM public.{table}"
                ).fetchone()
            break
        except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
            if time.monotonic() >= deadline:
                raise SystemExit(
                    f"Source {source} indisponible après 180 s. Volume conservé."
                )
            time.sleep(2)
    print(f"{source} | {role} | transaction_read_only={readonly} | {table}={count}")
    if (role, readonly, count) != ("agent_ro", "on", expected):
        raise SystemExit("Écart au contrôle de restauration. Volume conservé.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("source", choices=SOURCES)
    args = parser.parse_args()
    restore(args.folder, args.source)
