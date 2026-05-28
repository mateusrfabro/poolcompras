"""Versao do app + revisao Alembic atualmente aplicada.

Usado pelo splash banner do boot (logs) e pelo endpoint /health (JSON).

Pipeline /deploy_aggron do Ademar consegue:
- ler o splash banner no log pra confirmar que subiu commit certo
- chamar curl /health e parsear migration_head pra detectar
  "container subiu com codigo novo mas migration nao aplicou"
  (cenario exato do bug 1+2 de 2026-05-27).

Tudo eh resolvido lazy, com cache em modulo. Calcula 1x por processo.
"""
import logging
import os
import subprocess
from pathlib import Path

from alembic.migration import MigrationContext

from app import db

_log = logging.getLogger(__name__)

# Cache em modulo: cada um eh sentinel ate 1a chamada bem-sucedida.
_VERSION_CACHE: str | None = None
_MIGRATION_CACHE: str | None = None


def app_version() -> str:
    """SHA curto do commit atual (7 chars), ou valor de APP_VERSION env,
    ou 'unknown' se nada disso resolver.

    Estrategia:
    1. APP_VERSION env (Dockerfile pode injetar via ARG no build).
    2. `git rev-parse --short HEAD` (dev local + container que monta .git).
    3. Le .git/HEAD + ref file direto (fallback se git CLI nao tem).
    4. 'unknown'.
    """
    global _VERSION_CACHE
    if _VERSION_CACHE is not None:
        return _VERSION_CACHE

    env_v = os.environ.get("APP_VERSION", "").strip()
    if env_v:
        _VERSION_CACHE = env_v[:12]  # limita tamanho
        return _VERSION_CACHE

    # git CLI
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=2,
        )
        sha = out.decode("ascii", errors="ignore").strip()
        if sha:
            _VERSION_CACHE = sha
            return _VERSION_CACHE
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        pass

    # Leitura direta de .git/HEAD (container sem git CLI mas com .git montado)
    try:
        head = Path(".git/HEAD")
        if head.is_file():
            content = head.read_text(encoding="ascii", errors="ignore").strip()
            if content.startswith("ref:"):
                ref_path = Path(".git") / content.split(" ", 1)[1].strip()
                if ref_path.is_file():
                    sha = ref_path.read_text(encoding="ascii", errors="ignore").strip()
                    _VERSION_CACHE = sha[:7]
                    return _VERSION_CACHE
            else:
                _VERSION_CACHE = content[:7]
                return _VERSION_CACHE
    except OSError:
        pass

    _VERSION_CACHE = "unknown"
    return _VERSION_CACHE


def migration_head() -> str:
    """Revisao Alembic atualmente aplicada no DB (le tabela alembic_version).

    Retorna 'unknown' se nao conseguir ler (DB capotado, tabela ausente).
    NAO levanta — endpoint /health usa isso e nao pode quebrar por causa do
    helper de observabilidade.
    """
    global _MIGRATION_CACHE
    # Migration head MUDA entre uma chamada e outra (deploy aplica nova migration
    # sem restart do worker em alguns cenarios). Cacheamos so pra evitar custo
    # repetido dentro da MESMA execucao da request — recalcula no proximo hit.
    # Decisao: nao cachear. Custo eh ~1 SELECT por hit em /health, irrelevante.
    try:
        with db.engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            rev = ctx.get_current_revision() or "none"
            return rev
    except Exception:
        _log.warning("MIGRATION_HEAD_FAIL", exc_info=True)
        return "unknown"


def _reset_cache_for_tests() -> None:
    """Test helper — limpa cache de app_version. Nao usar em prod."""
    global _VERSION_CACHE, _MIGRATION_CACHE
    _VERSION_CACHE = None
    _MIGRATION_CACHE = None
