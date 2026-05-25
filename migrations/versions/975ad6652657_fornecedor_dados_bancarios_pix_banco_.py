"""Fornecedor: dados bancarios (pix, banco, agencia, conta)

Revision ID: 975ad6652657
Revises: 4f92e19ce81a
Create Date: 2026-04-17 09:33:34.856781

Reescrita idempotente (2026-05): baseline cria todas as colunas via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column


# revision identifiers, used by Alembic.
revision = '975ad6652657'
down_revision = '4f92e19ce81a'
branch_labels = None
depends_on = None


def upgrade():
    if not has_column('fornecedores', 'chave_pix'):
        with op.batch_alter_table('fornecedores', schema=None) as batch_op:
            batch_op.add_column(sa.Column('chave_pix', sa.String(length=150), nullable=True))
    if not has_column('fornecedores', 'banco'):
        with op.batch_alter_table('fornecedores', schema=None) as batch_op:
            batch_op.add_column(sa.Column('banco', sa.String(length=80), nullable=True))
    if not has_column('fornecedores', 'agencia'):
        with op.batch_alter_table('fornecedores', schema=None) as batch_op:
            batch_op.add_column(sa.Column('agencia', sa.String(length=20), nullable=True))
    if not has_column('fornecedores', 'conta'):
        with op.batch_alter_table('fornecedores', schema=None) as batch_op:
            batch_op.add_column(sa.Column('conta', sa.String(length=30), nullable=True))


def downgrade():
    for col in ('conta', 'agencia', 'banco', 'chave_pix'):
        if has_column('fornecedores', col):
            with op.batch_alter_table('fornecedores', schema=None) as batch_op:
                batch_op.drop_column(col)
