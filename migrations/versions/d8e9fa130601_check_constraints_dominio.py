"""CheckConstraints de dominio: preco>0, qtd>0, estrelas BETWEEN 1 AND 5.

Revision ID: d8e9fa130601
Revises: c7d8e9fa1205
Create Date: 2026-04-24

Move validacoes de range pro DB. Hoje so havia validacao na camada app —
um INSERT direto via SQL podia inserir preco_unitario=0 ou estrelas=10.

Reescrita idempotente (2026-05): baseline cria check constraints via metadata.
Nota: SQLite inspector pode nao reportar checks; o helper has_check faz
fallback pra False, entao em SQLite a constraint pode ser tentada de novo.
batch_alter_table em SQLite recria a tabela inteira — se uma constraint
de mesmo nome ja vier do CREATE original, SQLAlchemy detecta e nao duplica.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_check


revision = "d8e9fa130601"
down_revision = "c7d8e9fa1205"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite: has_check pode retornar False mesmo quando existe. Mas
    # batch_alter_table recria a tabela inteira e SQLAlchemy nao duplica
    # constraints existentes com o mesmo nome (defined via metadata reflection).
    # Em Postgres has_check funciona; pula corretamente.
    if not has_check('itens_pedido', 'ck_item_pedido_qtd_positiva'):
        with op.batch_alter_table("itens_pedido") as batch_op:
            batch_op.create_check_constraint(
                "ck_item_pedido_qtd_positiva",
                "quantidade > 0",
            )
    if not has_check('cotacoes', 'ck_cotacao_preco_positivo'):
        with op.batch_alter_table("cotacoes") as batch_op:
            batch_op.create_check_constraint(
                "ck_cotacao_preco_positivo",
                "preco_unitario > 0",
            )
    if not has_check('participacoes_rodada', 'ck_participacao_avaliacao_1a5'):
        with op.batch_alter_table("participacoes_rodada") as batch_op:
            batch_op.create_check_constraint(
                "ck_participacao_avaliacao_1a5",
                "avaliacao_geral IS NULL OR avaliacao_geral BETWEEN 1 AND 5",
            )
    if not has_check('avaliacoes_rodada', 'ck_avaliacao_estrelas_1a5'):
        with op.batch_alter_table("avaliacoes_rodada") as batch_op:
            batch_op.create_check_constraint(
                "ck_avaliacao_estrelas_1a5",
                "estrelas BETWEEN 1 AND 5",
            )


def downgrade():
    if has_check('avaliacoes_rodada', 'ck_avaliacao_estrelas_1a5'):
        with op.batch_alter_table("avaliacoes_rodada") as batch_op:
            batch_op.drop_constraint("ck_avaliacao_estrelas_1a5", type_="check")
    if has_check('participacoes_rodada', 'ck_participacao_avaliacao_1a5'):
        with op.batch_alter_table("participacoes_rodada") as batch_op:
            batch_op.drop_constraint("ck_participacao_avaliacao_1a5", type_="check")
    if has_check('cotacoes', 'ck_cotacao_preco_positivo'):
        with op.batch_alter_table("cotacoes") as batch_op:
            batch_op.drop_constraint("ck_cotacao_preco_positivo", type_="check")
    if has_check('itens_pedido', 'ck_item_pedido_qtd_positiva'):
        with op.batch_alter_table("itens_pedido") as batch_op:
            batch_op.drop_constraint("ck_item_pedido_qtd_positiva", type_="check")
