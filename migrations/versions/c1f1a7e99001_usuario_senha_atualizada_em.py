"""usuario_senha_atualizada_em

Adiciona coluna Usuario.senha_atualizada_em pra invalidar tokens de reset
de senha e sessoes ativas quando o usuario troca a senha.

Revision ID: c1f1a7e99001
Revises: 9ec8712ed82a
Create Date: 2026-04-22

Reescrita idempotente (2026-05): baseline cria coluna via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column


revision = "c1f1a7e99001"
down_revision = "9ec8712ed82a"
branch_labels = None
depends_on = None


def upgrade():
    if not has_column('usuarios', 'senha_atualizada_em'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.add_column(sa.Column("senha_atualizada_em", sa.DateTime(), nullable=True))


def downgrade():
    if has_column('usuarios', 'senha_atualizada_em'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.drop_column("senha_atualizada_em")
