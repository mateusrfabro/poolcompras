"""Drop Usuario.is_admin — fonte dupla com tipo='admin'.

Revision ID: c7d8e9fa1205
Revises: b6c7d8e9f104
Create Date: 2026-04-23

is_admin virou @property que deriva de tipo='admin'. Coluna legada pode cair.

Reescrita idempotente (2026-05): baseline NAO cria is_admin (model nao tem
mais a coluna). Em DB limpo, a coluna nao existe; o UPDATE deve ser skipado.
Em DB legado pre-baseline pode existir; drop normal.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column


revision = "c7d8e9fa1205"
down_revision = "b6c7d8e9f104"
branch_labels = None
depends_on = None


def upgrade():
    if has_column('usuarios', 'is_admin'):
        # Garante que nao ha usuario com is_admin=True sem tipo='admin' (defesa).
        # TRUE em vez de 1: Postgres tem tipo BOOLEAN estrito.
        op.execute(
            "UPDATE usuarios SET tipo = 'admin' "
            "WHERE is_admin = TRUE AND tipo != 'admin'"
        )
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.drop_column("is_admin")


def downgrade():
    if not has_column('usuarios', 'is_admin'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.add_column(sa.Column("is_admin", sa.Boolean(), nullable=True,
                                           server_default=sa.false()))
        # Restaura is_admin=True pra todos os admins atuais.
        op.execute(
            "UPDATE usuarios SET is_admin = TRUE WHERE tipo = 'admin'"
        )
