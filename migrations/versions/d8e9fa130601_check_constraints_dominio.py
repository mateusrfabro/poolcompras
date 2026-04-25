"""CheckConstraints de dominio: preco>0, qtd>0, estrelas BETWEEN 1 AND 5.

Revision ID: d8e9fa130601
Revises: c7d8e9fa1205
Create Date: 2026-04-24

Move validacoes de range pro DB. Hoje so havia validacao na camada app —
um INSERT direto via SQL podia inserir preco_unitario=0 ou estrelas=10.
"""
from alembic import op
import sqlalchemy as sa


revision = "d8e9fa130601"
down_revision = "c7d8e9fa1205"
branch_labels = None
depends_on = None


def upgrade():
    # ItemPedido.quantidade > 0
    with op.batch_alter_table("itens_pedido") as batch_op:
        batch_op.create_check_constraint(
            "ck_item_pedido_qtd_positiva",
            "quantidade > 0",
        )
    # Cotacao.preco_unitario > 0
    with op.batch_alter_table("cotacoes") as batch_op:
        batch_op.create_check_constraint(
            "ck_cotacao_preco_positivo",
            "preco_unitario > 0",
        )
    # ParticipacaoRodada.avaliacao_geral entre 1 e 5 (ou NULL)
    with op.batch_alter_table("participacoes_rodada") as batch_op:
        batch_op.create_check_constraint(
            "ck_participacao_avaliacao_1a5",
            "avaliacao_geral IS NULL OR avaliacao_geral BETWEEN 1 AND 5",
        )
    # AvaliacaoRodada.estrelas entre 1 e 5
    with op.batch_alter_table("avaliacoes_rodada") as batch_op:
        batch_op.create_check_constraint(
            "ck_avaliacao_estrelas_1a5",
            "estrelas BETWEEN 1 AND 5",
        )


def downgrade():
    with op.batch_alter_table("avaliacoes_rodada") as batch_op:
        batch_op.drop_constraint("ck_avaliacao_estrelas_1a5", type_="check")
    with op.batch_alter_table("participacoes_rodada") as batch_op:
        batch_op.drop_constraint("ck_participacao_avaliacao_1a5", type_="check")
    with op.batch_alter_table("cotacoes") as batch_op:
        batch_op.drop_constraint("ck_cotacao_preco_positivo", type_="check")
    with op.batch_alter_table("itens_pedido") as batch_op:
        batch_op.drop_constraint("ck_item_pedido_qtd_positiva", type_="check")
