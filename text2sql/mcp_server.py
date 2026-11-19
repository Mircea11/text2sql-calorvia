"""Unique détenteur des connexions sources ; six outils MCP via stdio.

Lancer par le client, jamais dans une cellule bloquante. Aucun accès DB ou GPU
n'a lieu à l'import. Les messages de diagnostic doivent rester sur stderr.
"""

from typing import Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .catalog import load_catalog
from .config import Settings
from .sources import SourceService

mcp = MCPServer("calorvia-text2sql")
_service = None


def service():
    global _service
    if _service is None:
        _service = SourceService(Settings.load(), load_catalog())
    return _service


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def list_sources() -> list[dict]:
    """Liste les trois bases, moteurs, périodes et nombres de tables."""
    return service().list_sources()


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def list_tables(source: Literal["erp", "compta", "paie"]) -> list[dict]:
    """Liste les tables de la source et compte leurs lignes."""
    return service().list_tables(source)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_table_card(source: Literal["erp", "compta", "paie"], table: str) -> dict:
    """Décrit colonnes, types, PK/FK, commentaires, codes, volume et termes métier."""
    return service().get_table_card(source, table)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def find_values(source: Literal["erp", "compta", "paie"], table: str, column: str, value: str) -> dict:
    """Recherche l'orthographe réelle d'un nom ou code, hors données personnelles."""
    return service().find_values(source, table, column, value)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def validate_sql(source: Literal["erp", "compta", "paie"], sql: str) -> dict:
    """Valide un SELECT dans le dialecte source, contrôle les colonnes et borne les lignes."""
    return service().validate_sql(source, sql)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def execute_sql(source: Literal["erp", "compta", "paie"], sql: str) -> dict:
    """Revalide et exécute via agent_ro ; renvoie SQL, source, colonnes, lignes et troncature."""
    return service().execute_sql(source, sql)


if __name__ == "__main__":
    mcp.run()
