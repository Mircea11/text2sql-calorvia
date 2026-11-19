"""Configuration locale partagée : endpoints existants, jamais de chargement GPU.

Lit les paramètres de l'environnement puis les fichiers .env existants, sans les
réécrire. Les connexions aux sources sont exclusivement utilisées par le MCP.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent


def local_url(value: str) -> str:
    """Refuse un endpoint distant : les données du laboratoire restent locales."""
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Endpoint HTTP local obligatoire (localhost/127.0.0.1/::1)")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Ne pas placer de secret ou de paramètres dans un endpoint")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    llm_url: str = ""
    llm_model: str = ""
    llm_key: str = "local"
    api_key: str = ""
    erp_port: int = 14330
    compta_port: int = 5433
    paie_port: int = 5434
    source_password: str = ""
    journal_dsn: str = ""
    max_rows: int = 200
    timeout_s: int = 30
    max_steps: int = 18

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(ROOT / ".env", override=False)
        load_dotenv(HERE / ".env", override=False)
        return cls(
            llm_url=os.getenv("T2SQL_LLM_URL", os.getenv("CALORVIA_LLM_BASE_URL", "")),
            llm_model=os.getenv("T2SQL_LLM_MODEL", os.getenv("CALORVIA_LLM_MODEL", "")),
            llm_key=os.getenv("T2SQL_LLM_KEY", os.getenv("CALORVIA_LLM_API_KEY", "local")),
            api_key=os.getenv("T2SQL_API_KEY", ""),
            erp_port=int(os.getenv("T2SQL_ERP_PORT", "14330")),
            compta_port=int(os.getenv("T2SQL_COMPTA_PORT", "5433")),
            paie_port=int(os.getenv("T2SQL_PAIE_PORT", "5434")),
            source_password=os.getenv("T2SQL_SOURCE_PASSWORD", os.getenv("AGENT_RO_PASSWORD", "")),
            journal_dsn=os.getenv("T2SQL_JOURNAL_DSN", ""),
            max_rows=min(1000, max(1, int(os.getenv("T2SQL_MAX_ROWS", "200")))),
            timeout_s=min(30, max(1, int(os.getenv("T2SQL_TIMEOUT_S", "30")))),
            max_steps=min(30, max(2, int(os.getenv("T2SQL_MAX_STEPS", "18")))),
        )

    def require_llm(self) -> None:
        if not self.llm_url or not self.llm_model:
            raise ValueError("Configurer le LLM existant : CALORVIA_LLM_BASE_URL/MODEL ou T2SQL_LLM_URL/MODEL")
        local_url(self.llm_url)


SOURCES = {
    "erp": {"database": "GESPRO", "dialect": "tsql", "schema": "dbo", "port_setting": "erp_port"},
    "compta": {"database": "compta", "dialect": "postgres", "schema": "public", "port_setting": "compta_port"},
    "paie": {"database": "paie", "dialect": "postgres", "schema": "public", "port_setting": "paie_port"},
}
