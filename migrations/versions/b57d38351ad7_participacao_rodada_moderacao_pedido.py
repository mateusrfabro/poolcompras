"""participacao_rodada_moderacao_pedido

Revision ID: b57d38351ad7
Revises: c40a4549b4d8
Create Date: 2026-04-18 15:23:03.617307

Reescrita idempotente (2026-05): baseline cria colunas via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column, has_fk


# revision identifiers, used by Alembic.
revision = 'b57d38351ad7'
down_revision = 'c40a4549b4d8'
branch_labels = None
depends_on = None


def upgrade():
    if not has_column('participacoes_rodada', 'pedido_enviado_em'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.add_column(sa.Column('pedido_enviado_em', sa.DateTime(), nullable=True))
    if not has_column('participacoes_rodada', 'pedido_aprovado_em'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.add_column(sa.Column('pedido_aprovado_em', sa.DateTime(), nullable=True))
    if not has_column('participacoes_rodada', 'pedido_aprovado_por_id'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.add_column(sa.Column('pedido_aprovado_por_id', sa.Integer(), nullable=True))
    if not has_column('participacoes_rodada', 'pedido_devolvido_em'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.add_column(sa.Column('pedido_devolvido_em', sa.DateTime(), nullable=True))
    if not has_column('participacoes_rodada', 'pedido_motivo_devolucao'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.add_column(sa.Column('pedido_motivo_devolucao', sa.String(length=500), nullable=True))
    if not has_column('participacoes_rodada', 'pedido_reprovado_em'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.add_column(sa.Column('pedido_reprovado_em', sa.DateTime(), nullable=True))
    if not has_fk('participacoes_rodada', 'fk_participacao_pedido_aprovado_por'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.create_foreign_key('fk_participacao_pedido_aprovado_por', 'usuarios', ['pedido_aprovado_por_id'], ['id'])


def downgrade():
    if has_fk('participacoes_rodada', 'fk_participacao_pedido_aprovado_por'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.drop_constraint('fk_participacao_pedido_aprovado_por', type_='foreignkey')
    for col in ('pedido_reprovado_em', 'pedido_motivo_devolucao', 'pedido_devolvido_em',
                'pedido_aprovado_por_id', 'pedido_aprovado_em', 'pedido_enviado_em'):
        if has_column('participacoes_rodada', col):
            with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
                batch_op.drop_column(col)
