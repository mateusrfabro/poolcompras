"""marketplace opt-in + chat_id BigInteger/index/unique

Revision ID: f4a2c9d81b05
Revises: e3a4b5c6d701
Create Date: 2026-04-23

Reescrita idempotente (2026-05):
- aparece_no_marketplace: skip se coluna existe.
- telegram_chat_id String->BigInteger: skip se indice unique ja existe
  (significa que ja foi promovida OU baseline criou direto no tipo final).
  Senao, dropa coluna String e recria como BigInteger + indice.

ATENCAO — downgrade NAO eh seguro em prod: drop_column + add_column nao
preserva chat_ids existentes. Se a base ja tem usuarios com Telegram opt-in,
rodar downgrade -> upgrade desconecta todos. Use apenas em dev/test.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column, has_index


revision = "f4a2c9d81b05"
down_revision = "e3a4b5c6d701"
branch_labels = None
depends_on = None


def upgrade():
    # Fornecedor.aparece_no_marketplace (opt-in LGPD)
    if not has_column('fornecedores', 'aparece_no_marketplace'):
        with op.batch_alter_table("fornecedores") as batch_op:
            batch_op.add_column(sa.Column("aparece_no_marketplace", sa.Boolean(), nullable=True))
        # TRUE/FALSE em vez de 1/0: Postgres tem tipo BOOLEAN estrito.
        op.execute("UPDATE fornecedores SET aparece_no_marketplace = FALSE WHERE aparece_no_marketplace IS NULL")
        with op.batch_alter_table("fornecedores") as batch_op:
            batch_op.alter_column("aparece_no_marketplace", nullable=False, server_default=sa.false())

    # Usuario.telegram_chat_id: String(32) -> BigInteger + index + unique.
    # Em DB limpo baseline ja criou como BigInteger com indice; pular.
    # Em DB legado: dropa e recria.
    if not has_index('usuarios', 'ix_usuarios_telegram_chat_id'):
        with op.batch_alter_table("usuarios") as batch_op:
            if has_column('usuarios', 'telegram_chat_id'):
                batch_op.drop_column("telegram_chat_id")
            batch_op.add_column(sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
            batch_op.create_index("ix_usuarios_telegram_chat_id", ["telegram_chat_id"], unique=True)


def downgrade():
    if has_index('usuarios', 'ix_usuarios_telegram_chat_id'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.drop_index("ix_usuarios_telegram_chat_id")
            batch_op.drop_column("telegram_chat_id")
            batch_op.add_column(sa.Column("telegram_chat_id", sa.String(32), nullable=True))

    if has_column('fornecedores', 'aparece_no_marketplace'):
        with op.batch_alter_table("fornecedores") as batch_op:
            batch_op.drop_column("aparece_no_marketplace")
