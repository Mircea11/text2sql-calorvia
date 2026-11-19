"""Journal PostgreSQL local : pas d'exécution de source sans journal disponible."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager

import psycopg
from psycopg import sql as pgsql
from psycopg.conninfo import conninfo_to_dict


class Journal:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.container=os.getenv("T2SQL_JOURNAL_CONTAINER","helpdesk-ops-postgres-1")
        if dsn:
            info = conninfo_to_dict(dsn)
            if info.get("host", "") not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Le journal PostgreSQL doit rester local")
        elif not shutil.which("docker") or not re.fullmatch(r"[A-Za-z0-9_.-]+",self.container):
            raise ValueError("Configurer le journal local par T2SQL_JOURNAL_DSN ou le conteneur Docker existant")

    def execute(self, statement: str) -> None:
        """Écrit dans le journal existant via DSN ou transport Docker déjà utilisé par Calorvia."""
        if self.dsn:
            with psycopg.connect(self.dsn,connect_timeout=5) as con:con.execute(statement)
        else:
            completed=subprocess.run(["docker","exec","-i",self.container,"psql","-X","-q","-U","calorvia_app","-d","calorvia_rag","-v","ON_ERROR_STOP=1","-f","-"],input=statement,capture_output=True,text=True,timeout=15)
            if completed.returncode:raise RuntimeError("Journal Docker indisponible ou compte écrivain insuffisant ; configurer T2SQL_JOURNAL_DSN")

    def initialize(self) -> None:
        from .config import HERE
        self.execute((HERE/"journal.sql").read_text())

    def experiment(self, payload: dict) -> None:
        values=[payload["id"],payload["git_commit"],payload["git_dirty"],json.dumps({k:v for k,v in payload.items() if k!="results"}),json.dumps(payload["results"],ensure_ascii=False)]
        query=pgsql.SQL("INSERT INTO text2sql_journal.experiments(id,git_commit,git_dirty,config,results) VALUES ({},{},{},{}::jsonb,{}::jsonb)").format(*[pgsql.Literal(v) for v in values])
        self.execute(query.as_string())

    def record(self, *, question: str, source: str, sql: str, stage: str, **details) -> None:
        """Enregistre une observation ; une indisponibilité n'est jamais masquée."""
        values=[question,source,sql,stage,json.dumps(details,ensure_ascii=False,default=str)]
        query=pgsql.SQL("INSERT INTO text2sql_journal.events(question,source,sql,stage,details) VALUES ({},{},{},{},{}::jsonb)").format(*[pgsql.Literal(v) for v in values])
        self.execute(query.as_string())

    @contextmanager
    def access(self, question: str, source: str, sql: str):
        started = time.monotonic()
        self.record(question=question, source=source, sql=sql, stage="started")
        result = {}
        try:
            yield result
        except Exception as exc:
            self.record(question=question, source=source, sql=sql, stage="error", error=type(exc).__name__, duration_s=time.monotonic()-started)
            raise
        else:
            self.record(question=question, source=source, sql=sql, stage="done", duration_s=time.monotonic()-started, **result)
