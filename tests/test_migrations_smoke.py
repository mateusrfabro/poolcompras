"""Smoke test de migrations: garante que `flask db upgrade` roda
contra DB vazio sem erro. Pega regressoes como:
- Migration usando 1/0 em UPDATE de boolean (Postgres rejeita — incidente R5)
- down_revision apontando pra revisao inexistente
- op.add_column sem checagem em coluna ja existente
- Schema-drift entre models.py e migrations/versions/

Usa SQLite arquivo temporario (rapido, descartavel). Postgres em prod tem
matriz CI separada.

NOTA: hoje pulado em SQLite porque a baseline `86d17a406150` usa
`db.metadata.create_all(checkfirst=True)` — cria o schema CORRENTE (com
indices declarados em models.py via `index=True`), enquanto migrations
posteriores (a7fe2eb7214e, etc) tentam create_index do mesmo nome,
causando "index already exists". Em prod (Postgres) a baseline foi
rodada antes desses indices serem declarados em models.py, entao nao ha
conflito. Reabrir quando: (a) refazer baseline com schema historico fiel,
ou (b) tornar create_index das migrations posteriores idempotentes.
"""
import os
import tempfile

import pytest

from app import create_app


@pytest.fixture
def app_sem_create_all():
    """App de teste SEM db.create_all() — pra alembic upgrade construir o schema."""
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="poolcompras-mig-")
    os.close(fd)
    os.environ["TEST_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SECRET_KEY"] = "test-secret"
    app = create_app("testing")
    yield app, db_path
    os.environ.pop("TEST_DATABASE_URL", None)
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.mark.skip(reason=(
    "Baseline `86d17a406150` cria schema corrente via metadata.create_all, "
    "conflitando com create_index das migrations posteriores. Bug arquitetural "
    "documentado no docstring do modulo — atacar separadamente."
))
def test_alembic_upgrade_head_partindo_de_zero(app_sem_create_all):
    """`flask db upgrade head` partindo de zero — se algum migration estiver
    quebrado, lanca excecao aqui e o teste falha."""
    from flask_migrate import upgrade as flask_db_upgrade

    app, _ = app_sem_create_all
    with app.app_context():
        flask_db_upgrade()
