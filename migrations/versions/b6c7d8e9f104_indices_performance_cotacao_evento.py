"""Indices compostos pra queries hot: Cotacao(rodada,fornecedor), Cotacao(rodada,produto),
EventoRodada(rodada,criado_em), ParticipacaoRodada partial (pedido pendente).

Revision ID: b6c7d8e9f104
Revises: a5b6c7d8e903
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa


revision = "b6c7d8e9f104"
down_revision = "a5b6c7d8e903"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cotacoes") as batch_op:
        batch_op.create_index(
            "ix_cotacao_rodada_fornecedor",
            ["rodada_id", "fornecedor_id"],
        )
        batch_op.create_index(
            "ix_cotacao_rodada_produto",
            ["rodada_id", "produto_id"],
        )

    with op.batch_alter_table("eventos_rodada") as batch_op:
        batch_op.create_index(
            "ix_evento_rodada_criado",
            ["rodada_id", "criado_em"],
        )

    # Partial index: fila de moderacao (pedido enviado sem decisao).
    # batch_alter_table nao expoe postgresql_where/sqlite_where; usar op.execute.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            'CREATE INDEX IF NOT EXISTS ix_participacao_pedido_pendente '
            'ON participacoes_rodada (rodada_id) '
            'WHERE pedido_enviado_em IS NOT NULL '
            'AND pedido_aprovado_em IS NULL '
            'AND pedido_reprovado_em IS NULL'
        )
    else:
        # SQLite
        op.execute(
            'CREATE INDEX IF NOT EXISTS ix_participacao_pedido_pendente '
            'ON participacoes_rodada (rodada_id) '
            'WHERE pedido_enviado_em IS NOT NULL '
            'AND pedido_aprovado_em IS NULL '
            'AND pedido_reprovado_em IS NULL'
        )


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_participacao_pedido_pendente')

    with op.batch_alter_table("eventos_rodada") as batch_op:
        batch_op.drop_index("ix_evento_rodada_criado")

    with op.batch_alter_table("cotacoes") as batch_op:
        batch_op.drop_index("ix_cotacao_rodada_produto")
        batch_op.drop_index("ix_cotacao_rodada_fornecedor")
