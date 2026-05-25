"""usuario_telegram_chat_id

Adiciona coluna Usuario.telegram_chat_id (String 32, nullable).

Revision ID: e3a4b5c6d701
Revises: d2b4e5a81f02
Create Date: 2026-04-23

Reescrita idempotente (2026-05): baseline cria a coluna ja como BigInteger
(o tipo final do model atual). Em DB ja migrado tambem ja existe (talvez
String, sera promovida em f4a2c9d81b05). Guard simples: pular se ja existe.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column


revision = "e3a4b5c6d701"
down_revision = "d2b4e5a81f02"
branch_labels = None
depends_on = None


def upgrade():
    if not has_column('usuarios', 'telegram_chat_id'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.add_column(sa.Column("telegram_chat_id", sa.String(32), nullable=True))


def downgrade():
    if has_column('usuarios', 'telegram_chat_id'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.drop_column("telegram_chat_id")
