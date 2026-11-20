"""Restaure GESPRO sur le Z4 avec le Compose et le script sqlcmd du cours.

Entrée : le dossier docker des sources, dont le .env a servi aux deux PostgreSQL.
Sortie : identité de connexion et nombre de factures, lus avec agent_ro.
Le nom fixe du conteneur de restauration empêche deux imports concurrents.
"""

import argparse
import os
import socket
import subprocess
from pathlib import Path

import pymssql
from dotenv import dotenv_values

OVERRIDE = """services:
  erp-sqlserver:
    ports: !override ["127.0.0.1:14330:1433"]
    environment:
      MSSQL_MEMORY_LIMIT_MB: "2048"
"""


def restore(folder):
    """Démarre seulement SQL Server, importe si GESPRO est absente, puis compte."""
    folder = folder.resolve()
    values = dotenv_values(folder / ".env", interpolate=False)
    if not values.get("AGENT_RO_PASSWORD") or not values.get("MSSQL_SA_PASSWORD"):
        raise SystemExit("Le .env privé issu de la restauration comptable est requis.")

    endpoint = os.environ.get("DOCKER_HOST")
    if not endpoint or os.environ.get("DOCKER_CONTEXT"):
        endpoint = subprocess.check_output(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            text=True,
        ).strip()
    if not endpoint.startswith("unix://"):
        raise SystemExit("Ce script utilise uniquement le Docker local du Z4.")
    # Si le port est occupé, seule l'instance attendue peut être réutilisée.
    with socket.socket() as sock:
        occupied = sock.connect_ex(("127.0.0.1", 14330)) == 0
    if occupied:
        bindings = subprocess.check_output(
            ["docker", "port", "calorvia-erp", "1433/tcp"], text=True
        ).splitlines()
        if bindings != ["127.0.0.1:14330"]:
            raise SystemExit("Port 14330 occupé, propriétaire ou liaison inattendus.")

    def compose(*args):
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
                *args,
            ],
            cwd=folder,
            input=OVERRIDE,
            text=True,
            check=True,
            env={
                **os.environ,
                "MSSQL_SA_PASSWORD": values["MSSQL_SA_PASSWORD"],
                "AGENT_RO_PASSWORD": values["AGENT_RO_PASSWORD"],
                "FORCE_RESTORE": "0",
            },
        )

    compose("up", "-d", "--no-deps", "--no-recreate", "--wait", "erp-sqlserver")
    compose(
        "run",
        "--rm",
        "-T",
        "--no-deps",
        "--name",
        "calorvia-erp-restore",
        "erp-restore",
    )
    with (
        pymssql.connect(
            server="127.0.0.1",
            port=14330,
            database="GESPRO",
            user="agent_ro",
            password=values["AGENT_RO_PASSWORD"],
            login_timeout=10,
            timeout=30,
        ) as conn,
        conn.cursor() as cursor,
    ):
        cursor.execute("SELECT SUSER_SNAME(), DB_NAME(), COUNT(*) FROM dbo.VTE_FACT")
        row = cursor.fetchone()
    if row != ("agent_ro", "GESPRO", 10185):
        raise SystemExit(f"Contrôle inattendu : {row!r}. Volume conservé.")
    print("erp | agent_ro | GESPRO | VTE_FACT=10185")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    restore(parser.parse_args().folder)
