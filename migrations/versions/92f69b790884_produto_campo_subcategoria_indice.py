"""Produto: campo subcategoria + indice

Revision ID: 92f69b790884
Revises: 975ad6652657
Create Date: 2026-04-18 13:57:15.345696

Reescrita idempotente (2026-05): baseline cria coluna/indices via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column, has_index


# revision identifiers, used by Alembic.
revision = '92f69b790884'
down_revision = '975ad6652657'
branch_labels = None
depends_on = None


def upgrade():
    if not has_column('produtos', 'subcategoria'):
        with op.batch_alter_table('produtos', schema=None) as batch_op:
            batch_op.add_column(sa.Column('subcategoria', sa.String(length=50), nullable=True))
    if not has_index('produtos', 'ix_produtos_categoria'):
        with op.batch_alter_table('produtos', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_produtos_categoria'), ['categoria'], unique=False)
    if not has_index('produtos', 'ix_produtos_subcategoria'):
        with op.batch_alter_table('produtos', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_produtos_subcategoria'), ['subcategoria'], unique=False)


def downgrade():
    if has_index('produtos', 'ix_produtos_subcategoria'):
        with op.batch_alter_table('produtos', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_produtos_subcategoria'))
    if has_index('produtos', 'ix_produtos_categoria'):
        with op.batch_alter_table('produtos', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_produtos_categoria'))
    if has_column('produtos', 'subcategoria'):
        with op.batch_alter_table('produtos', schema=None) as batch_op:
            batch_op.drop_column('subcategoria')
