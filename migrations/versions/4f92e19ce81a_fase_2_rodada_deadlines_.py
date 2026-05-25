"""Fase 2: Rodada deadlines + ParticipacaoRodada + AvaliacaoRodada + EventoRodada

Revision ID: 4f92e19ce81a
Revises: a7fe2eb7214e
Create Date: 2026-04-16 14:44:10.929416

Reescrita idempotente (2026-05): baseline cria todas as tabelas via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column, has_index, has_table


# revision identifiers, used by Alembic.
revision = '4f92e19ce81a'
down_revision = 'a7fe2eb7214e'
branch_labels = None
depends_on = None


def upgrade():
    if not has_table('avaliacoes_rodada'):
        op.create_table('avaliacoes_rodada',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rodada_id', sa.Integer(), nullable=False),
        sa.Column('lanchonete_id', sa.Integer(), nullable=False),
        sa.Column('fornecedor_id', sa.Integer(), nullable=False),
        sa.Column('estrelas', sa.Integer(), nullable=False),
        sa.Column('comentario', sa.String(length=500), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fornecedor_id'], ['fornecedores.id'], ),
        sa.ForeignKeyConstraint(['lanchonete_id'], ['lanchonetes.id'], ),
        sa.ForeignKeyConstraint(['rodada_id'], ['rodadas.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rodada_id', 'lanchonete_id', 'fornecedor_id', name='uq_avaliacao_rodada_lanchonete_fornecedor')
        )
    if not has_index('avaliacoes_rodada', 'ix_avaliacoes_rodada_fornecedor_id'):
        with op.batch_alter_table('avaliacoes_rodada', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_avaliacoes_rodada_fornecedor_id'), ['fornecedor_id'], unique=False)
    if not has_index('avaliacoes_rodada', 'ix_avaliacoes_rodada_lanchonete_id'):
        with op.batch_alter_table('avaliacoes_rodada', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_avaliacoes_rodada_lanchonete_id'), ['lanchonete_id'], unique=False)
    if not has_index('avaliacoes_rodada', 'ix_avaliacoes_rodada_rodada_id'):
        with op.batch_alter_table('avaliacoes_rodada', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_avaliacoes_rodada_rodada_id'), ['rodada_id'], unique=False)

    if not has_table('eventos_rodada'):
        op.create_table('eventos_rodada',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rodada_id', sa.Integer(), nullable=False),
        sa.Column('lanchonete_id', sa.Integer(), nullable=True),
        sa.Column('ator_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(length=40), nullable=False),
        sa.Column('descricao', sa.String(length=500), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['ator_id'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['lanchonete_id'], ['lanchonetes.id'], ),
        sa.ForeignKeyConstraint(['rodada_id'], ['rodadas.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not has_index('eventos_rodada', 'ix_eventos_rodada_criado_em'):
        with op.batch_alter_table('eventos_rodada', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_eventos_rodada_criado_em'), ['criado_em'], unique=False)
    if not has_index('eventos_rodada', 'ix_eventos_rodada_lanchonete_id'):
        with op.batch_alter_table('eventos_rodada', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_eventos_rodada_lanchonete_id'), ['lanchonete_id'], unique=False)
    if not has_index('eventos_rodada', 'ix_eventos_rodada_rodada_id'):
        with op.batch_alter_table('eventos_rodada', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_eventos_rodada_rodada_id'), ['rodada_id'], unique=False)

    if not has_table('participacoes_rodada'):
        op.create_table('participacoes_rodada',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rodada_id', sa.Integer(), nullable=False),
        sa.Column('lanchonete_id', sa.Integer(), nullable=False),
        sa.Column('aceite_proposta', sa.Boolean(), nullable=True),
        sa.Column('aceite_em', sa.DateTime(), nullable=True),
        sa.Column('comprovante_key', sa.String(length=255), nullable=True),
        sa.Column('comprovante_em', sa.DateTime(), nullable=True),
        sa.Column('pagamento_confirmado_em', sa.DateTime(), nullable=True),
        sa.Column('pagamento_confirmado_por_id', sa.Integer(), nullable=True),
        sa.Column('entrega_informada_em', sa.DateTime(), nullable=True),
        sa.Column('entrega_informada_por_id', sa.Integer(), nullable=True),
        sa.Column('entrega_data', sa.Date(), nullable=True),
        sa.Column('recebimento_ok', sa.Boolean(), nullable=True),
        sa.Column('recebimento_em', sa.DateTime(), nullable=True),
        sa.Column('recebimento_observacao', sa.String(length=500), nullable=True),
        sa.Column('avaliacao_geral', sa.Integer(), nullable=True),
        sa.Column('avaliacao_em', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entrega_informada_por_id'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['lanchonete_id'], ['lanchonetes.id'], ),
        sa.ForeignKeyConstraint(['pagamento_confirmado_por_id'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['rodada_id'], ['rodadas.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rodada_id', 'lanchonete_id', name='uq_participacao_rodada_lanchonete')
        )
    if not has_index('participacoes_rodada', 'ix_participacoes_rodada_lanchonete_id'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_participacoes_rodada_lanchonete_id'), ['lanchonete_id'], unique=False)
    if not has_index('participacoes_rodada', 'ix_participacoes_rodada_rodada_id'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_participacoes_rodada_rodada_id'), ['rodada_id'], unique=False)

    if not has_column('rodadas', 'deadline_pedido'):
        with op.batch_alter_table('rodadas', schema=None) as batch_op:
            batch_op.add_column(sa.Column('deadline_pedido', sa.DateTime(), nullable=True))
    if not has_column('rodadas', 'deadline_cotacao'):
        with op.batch_alter_table('rodadas', schema=None) as batch_op:
            batch_op.add_column(sa.Column('deadline_cotacao', sa.DateTime(), nullable=True))
    if not has_column('rodadas', 'deadline_aceite'):
        with op.batch_alter_table('rodadas', schema=None) as batch_op:
            batch_op.add_column(sa.Column('deadline_aceite', sa.DateTime(), nullable=True))
    if not has_column('rodadas', 'deadline_pagamento'):
        with op.batch_alter_table('rodadas', schema=None) as batch_op:
            batch_op.add_column(sa.Column('deadline_pagamento', sa.DateTime(), nullable=True))
    if not has_column('rodadas', 'deadline_entrega'):
        with op.batch_alter_table('rodadas', schema=None) as batch_op:
            batch_op.add_column(sa.Column('deadline_entrega', sa.DateTime(), nullable=True))
    if not has_column('rodadas', 'deadline_confirmacao'):
        with op.batch_alter_table('rodadas', schema=None) as batch_op:
            batch_op.add_column(sa.Column('deadline_confirmacao', sa.DateTime(), nullable=True))


def downgrade():
    for col in ('deadline_confirmacao', 'deadline_entrega', 'deadline_pagamento',
                'deadline_aceite', 'deadline_cotacao', 'deadline_pedido'):
        if has_column('rodadas', col):
            with op.batch_alter_table('rodadas', schema=None) as batch_op:
                batch_op.drop_column(col)

    if has_index('participacoes_rodada', 'ix_participacoes_rodada_rodada_id'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_participacoes_rodada_rodada_id'))
    if has_index('participacoes_rodada', 'ix_participacoes_rodada_lanchonete_id'):
        with op.batch_alter_table('participacoes_rodada', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_participacoes_rodada_lanchonete_id'))
    if has_table('participacoes_rodada'):
        op.drop_table('participacoes_rodada')

    if has_index('eventos_rodada', 'ix_eventos_rodada_rodada_id'):
        with op.batch_alter_table('eventos_rodada', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_eventos_rodada_rodada_id'))
    if has_index('eventos_rodada', 'ix_eventos_rodada_lanchonete_id'):
        with op.batch_alter_table('eventos_rodada', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_eventos_rodada_lanchonete_id'))
    if has_index('eventos_rodada', 'ix_eventos_rodada_criado_em'):
        with op.batch_alter_table('eventos_rodada', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_eventos_rodada_criado_em'))
    if has_table('eventos_rodada'):
        op.drop_table('eventos_rodada')

    if has_index('avaliacoes_rodada', 'ix_avaliacoes_rodada_rodada_id'):
        with op.batch_alter_table('avaliacoes_rodada', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_avaliacoes_rodada_rodada_id'))
    if has_index('avaliacoes_rodada', 'ix_avaliacoes_rodada_lanchonete_id'):
        with op.batch_alter_table('avaliacoes_rodada', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_avaliacoes_rodada_lanchonete_id'))
    if has_index('avaliacoes_rodada', 'ix_avaliacoes_rodada_fornecedor_id'):
        with op.batch_alter_table('avaliacoes_rodada', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_avaliacoes_rodada_fornecedor_id'))
    if has_table('avaliacoes_rodada'):
        op.drop_table('avaliacoes_rodada')
