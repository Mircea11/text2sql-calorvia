"""Exclusion des traitements Task 2 ; aucun contrôle des services du RAG.

Le verrou ne détecte pas la charge de Task 1 : réserver un créneau hors de son
évaluation avant une compilation NVIDIA ou une campagne de questions.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import fcntl

from .config import ROOT

_owned = ContextVar("text2sql_lock_owned", default=False)


@contextmanager
def exclusive_work():
    """Verrou interprocessus sans attente, libéré même sur erreur."""
    if _owned.get():
        yield
        return
    path = ROOT / "data" / "text2sql" / "runtime.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Un traitement Task 2 est déjà actif ; aucun lot concurrent lancé"
            ) from exc
        token = _owned.set(True)
        try:
            yield
        finally:
            _owned.reset(token)
            fcntl.flock(handle, fcntl.LOCK_UN)
