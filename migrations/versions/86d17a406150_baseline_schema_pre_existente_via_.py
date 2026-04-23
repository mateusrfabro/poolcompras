"""baseline — cria schema inicial (idempotente)

Revision ID: 86d17a406150
Revises:
Create Date: 2026-04-16 14:28:34.686666

Dev original foi `db.create_all()`. Essa migration estava vazia, o que
bloqueava `flask db upgrade` em DB Postgres limpo (nao criava nada).

Agora cria todas as tabelas declaradas no metadata *se ainda nao existirem*
(checkfirst=True). Dev: nada acontece (tabelas ja criadas via create_all).
Prod Postgres: bootstrap completo. Nao derruba ambiente existente.

Migrations subsequentes (92f69b79, etc) continuam rodando normalmente depois.
"""
from alembic import op
from app import db


revision = '86d17a406150'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Cria apenas tabelas faltantes — respeita DBs ja populados via create_all()
    bind = op.get_bind()
    db.metadata.create_all(bind=bind, checkfirst=True)


def downgrade():
    # Downgrade do baseline nao faz sentido em prod (dropar tudo).
    # Em dev, dropa todas as tabelas do metadata.
    bind = op.get_bind()
    db.metadata.drop_all(bind=bind, checkfirst=True)
