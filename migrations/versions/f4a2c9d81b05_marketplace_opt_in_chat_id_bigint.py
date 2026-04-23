"""marketplace opt-in + chat_id BigInteger/index/unique

Revision ID: f4a2c9d81b05
Revises: e3a4b5c6d701
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa


revision = "f4a2c9d81b05"
down_revision = "e3a4b5c6d701"
branch_labels = None
depends_on = None


def upgrade():
    # Fornecedor.aparece_no_marketplace (opt-in LGPD)
    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.add_column(sa.Column("aparece_no_marketplace", sa.Boolean(), nullable=True))
    op.execute("UPDATE fornecedores SET aparece_no_marketplace = 0 WHERE aparece_no_marketplace IS NULL")
    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.alter_column("aparece_no_marketplace", nullable=False, server_default=sa.false())

    # Usuario.telegram_chat_id: String(32) -> BigInteger + index + unique
    # Drop + recreate (SQLite nao faz alter_column limpo em type change)
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_column("telegram_chat_id")
        batch_op.add_column(sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
        batch_op.create_index("ix_usuarios_telegram_chat_id", ["telegram_chat_id"], unique=True)


def downgrade():
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_index("ix_usuarios_telegram_chat_id")
        batch_op.drop_column("telegram_chat_id")
        batch_op.add_column(sa.Column("telegram_chat_id", sa.String(32), nullable=True))

    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.drop_column("aparece_no_marketplace")
