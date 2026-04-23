"""Drop Usuario.is_admin — fonte dupla com tipo='admin'.

Revision ID: c7d8e9fa1205
Revises: b6c7d8e9f104
Create Date: 2026-04-23

is_admin virou @property que deriva de tipo='admin'. Coluna legada pode cair.
"""
from alembic import op
import sqlalchemy as sa


revision = "c7d8e9fa1205"
down_revision = "b6c7d8e9f104"
branch_labels = None
depends_on = None


def upgrade():
    # Garante que nao ha usuario com is_admin=True sem tipo='admin' (defesa)
    op.execute(
        "UPDATE usuarios SET tipo = 'admin' "
        "WHERE is_admin = 1 AND tipo != 'admin'"
    )
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_column("is_admin")


def downgrade():
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), nullable=True,
                                       server_default=sa.false()))
    # Restaura is_admin=True pra todos os admins atuais
    op.execute(
        "UPDATE usuarios SET is_admin = 1 WHERE tipo = 'admin'"
    )
