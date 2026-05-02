"""LGPD: usuario.aceite_termos_em

Revision ID: a1b2c3d4e5f6
Revises: e9fa130602
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "e9fa130602"
branch_labels = None
depends_on = None


def upgrade():
    # Usuario.aceite_termos_em: timestamp de aceite do checkbox de Termos+Privacidade.
    # Nullable pra preservar usuarios legacy sem dado historico — quando NULL,
    # UI pode forcar reaceite no proximo login. Usuarios novos sempre setam.
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(sa.Column("aceite_termos_em", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_column("aceite_termos_em")
