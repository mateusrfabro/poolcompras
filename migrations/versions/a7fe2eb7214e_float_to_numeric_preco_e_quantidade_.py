"""float to numeric (preco e quantidade) + indices nas FKs + unique constraint cotacao

Revision ID: a7fe2eb7214e
Revises: 86d17a406150
Create Date: 2026-04-16 14:29:39.560794

Reescrita idempotente (2026-05): a baseline (86d17a406150) cria todo o schema
final via create_all(checkfirst=True). Em DB limpo, esta migration tentaria
recriar indices que ja existem. Envelopamos cada DDL com has_index/has_uq.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_index, has_uq


# revision identifiers, used by Alembic.
revision = 'a7fe2eb7214e'
down_revision = '86d17a406150'
branch_labels = None
depends_on = None


def upgrade():
    # alter_column de Float->Numeric: idempotente na pratica (alterar pro mesmo
    # tipo eh no-op no SQLA). Mantemos sem guard.
    with op.batch_alter_table('cotacoes', schema=None) as batch_op:
        batch_op.alter_column('preco_unitario',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=12, scale=2),
               existing_nullable=False)
        batch_op.alter_column('quantidade_minima',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=10, scale=3),
               existing_nullable=True)

    # Indices: um batch por op pra evitar duplicacao em SQLite batch mode.
    if not has_index('cotacoes', 'ix_cotacoes_fornecedor_id'):
        with op.batch_alter_table('cotacoes', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_cotacoes_fornecedor_id'), ['fornecedor_id'], unique=False)
    if not has_index('cotacoes', 'ix_cotacoes_produto_id'):
        with op.batch_alter_table('cotacoes', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_cotacoes_produto_id'), ['produto_id'], unique=False)
    if not has_index('cotacoes', 'ix_cotacoes_rodada_id'):
        with op.batch_alter_table('cotacoes', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_cotacoes_rodada_id'), ['rodada_id'], unique=False)
    if not has_uq('cotacoes', 'uq_cotacao_rodada_fornecedor_produto'):
        with op.batch_alter_table('cotacoes', schema=None) as batch_op:
            batch_op.create_unique_constraint('uq_cotacao_rodada_fornecedor_produto', ['rodada_id', 'fornecedor_id', 'produto_id'])

    with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
        batch_op.alter_column('quantidade',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=10, scale=3),
               existing_nullable=False)

    if not has_index('itens_pedido', 'ix_itens_pedido_lanchonete_id'):
        with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_itens_pedido_lanchonete_id'), ['lanchonete_id'], unique=False)
    if not has_index('itens_pedido', 'ix_itens_pedido_produto_id'):
        with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_itens_pedido_produto_id'), ['produto_id'], unique=False)
    if not has_index('itens_pedido', 'ix_itens_pedido_rodada_id'):
        with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_itens_pedido_rodada_id'), ['rodada_id'], unique=False)
    if not has_index('itens_pedido', 'ix_itens_pedido_rodada_lanchonete'):
        with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
            batch_op.create_index('ix_itens_pedido_rodada_lanchonete', ['rodada_id', 'lanchonete_id'], unique=False)


def downgrade():
    if has_index('itens_pedido', 'ix_itens_pedido_rodada_lanchonete'):
        with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
            batch_op.drop_index('ix_itens_pedido_rodada_lanchonete')
    if has_index('itens_pedido', 'ix_itens_pedido_rodada_id'):
        with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_itens_pedido_rodada_id'))
    if has_index('itens_pedido', 'ix_itens_pedido_produto_id'):
        with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_itens_pedido_produto_id'))
    if has_index('itens_pedido', 'ix_itens_pedido_lanchonete_id'):
        with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_itens_pedido_lanchonete_id'))

    with op.batch_alter_table('itens_pedido', schema=None) as batch_op:
        batch_op.alter_column('quantidade',
               existing_type=sa.Numeric(precision=10, scale=3),
               type_=sa.FLOAT(),
               existing_nullable=False)

    if has_uq('cotacoes', 'uq_cotacao_rodada_fornecedor_produto'):
        with op.batch_alter_table('cotacoes', schema=None) as batch_op:
            batch_op.drop_constraint('uq_cotacao_rodada_fornecedor_produto', type_='unique')
    if has_index('cotacoes', 'ix_cotacoes_rodada_id'):
        with op.batch_alter_table('cotacoes', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_cotacoes_rodada_id'))
    if has_index('cotacoes', 'ix_cotacoes_produto_id'):
        with op.batch_alter_table('cotacoes', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_cotacoes_produto_id'))
    if has_index('cotacoes', 'ix_cotacoes_fornecedor_id'):
        with op.batch_alter_table('cotacoes', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_cotacoes_fornecedor_id'))

    with op.batch_alter_table('cotacoes', schema=None) as batch_op:
        batch_op.alter_column('quantidade_minima',
               existing_type=sa.Numeric(precision=10, scale=3),
               type_=sa.FLOAT(),
               existing_nullable=True)
        batch_op.alter_column('preco_unitario',
               existing_type=sa.Numeric(precision=12, scale=2),
               type_=sa.FLOAT(),
               existing_nullable=False)
