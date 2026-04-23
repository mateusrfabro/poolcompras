"""usuario_telegram_chat_id

Adiciona coluna Usuario.telegram_chat_id (String 32, nullable).

Revision ID: e3a4b5c6d701
Revises: d2b4e5a81f02
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa


revision = "e3a4b5c6d701"
down_revision = "d2b4e5a81f02"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(sa.Column("telegram_chat_id", sa.String(32), nullable=True))


def downgrade():
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_column("telegram_chat_id")
