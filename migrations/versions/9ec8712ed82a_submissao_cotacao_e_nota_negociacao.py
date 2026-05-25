"""submissao_cotacao_e_nota_negociacao

Revision ID: 9ec8712ed82a
Revises: b57d38351ad7
Create Date: 2026-04-18 17:39:37.693769

Reescrita idempotente (2026-05): baseline cria tabelas/indices via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_index, has_table


# revision identifiers, used by Alembic.
revision = '9ec8712ed82a'
down_revision = 'b57d38351ad7'
branch_labels = None
depends_on = None


def upgrade():
    if not has_table('submissoes_cotacao'):
        op.create_table('submissoes_cotacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rodada_id', sa.Integer(), nullable=False),
        sa.Column('fornecedor_id', sa.Integer(), nullable=False),
        sa.Column('enviada_em', sa.DateTime(), nullable=True),
        sa.Column('aprovada_em', sa.DateTime(), nullable=True),
        sa.Column('aprovada_por_id', sa.Integer(), nullable=True),
        sa.Column('devolvida_em', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['aprovada_por_id'], ['usuarios.id'], name='fk_submissao_aprovada_por'),
        sa.ForeignKeyConstraint(['fornecedor_id'], ['fornecedores.id'], ),
        sa.ForeignKeyConstraint(['rodada_id'], ['rodadas.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rodada_id', 'fornecedor_id', name='uq_submissao_rodada_fornecedor')
        )
    if not has_index('submissoes_cotacao', 'ix_submissoes_cotacao_fornecedor_id'):
        with op.batch_alter_table('submissoes_cotacao', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_submissoes_cotacao_fornecedor_id'), ['fornecedor_id'], unique=False)
    if not has_index('submissoes_cotacao', 'ix_submissoes_cotacao_rodada_id'):
        with op.batch_alter_table('submissoes_cotacao', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_submissoes_cotacao_rodada_id'), ['rodada_id'], unique=False)

    if not has_table('notas_negociacao'):
        op.create_table('notas_negociacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submissao_id', sa.Integer(), nullable=False),
        sa.Column('autor_tipo', sa.String(length=20), nullable=False),
        sa.Column('autor_usuario_id', sa.Integer(), nullable=False),
        sa.Column('texto', sa.String(length=1000), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['autor_usuario_id'], ['usuarios.id'], name='fk_nota_autor'),
        sa.ForeignKeyConstraint(['submissao_id'], ['submissoes_cotacao.id'], name='fk_nota_submissao'),
        sa.PrimaryKeyConstraint('id')
        )
    if not has_index('notas_negociacao', 'ix_notas_negociacao_criado_em'):
        with op.batch_alter_table('notas_negociacao', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_notas_negociacao_criado_em'), ['criado_em'], unique=False)
    if not has_index('notas_negociacao', 'ix_notas_negociacao_submissao_id'):
        with op.batch_alter_table('notas_negociacao', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_notas_negociacao_submissao_id'), ['submissao_id'], unique=False)


def downgrade():
    if has_index('notas_negociacao', 'ix_notas_negociacao_submissao_id'):
        with op.batch_alter_table('notas_negociacao', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_notas_negociacao_submissao_id'))
    if has_index('notas_negociacao', 'ix_notas_negociacao_criado_em'):
        with op.batch_alter_table('notas_negociacao', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_notas_negociacao_criado_em'))
    if has_table('notas_negociacao'):
        op.drop_table('notas_negociacao')

    if has_index('submissoes_cotacao', 'ix_submissoes_cotacao_rodada_id'):
        with op.batch_alter_table('submissoes_cotacao', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_submissoes_cotacao_rodada_id'))
    if has_index('submissoes_cotacao', 'ix_submissoes_cotacao_fornecedor_id'):
        with op.batch_alter_table('submissoes_cotacao', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_submissoes_cotacao_fornecedor_id'))
    if has_table('submissoes_cotacao'):
        op.drop_table('submissoes_cotacao')
