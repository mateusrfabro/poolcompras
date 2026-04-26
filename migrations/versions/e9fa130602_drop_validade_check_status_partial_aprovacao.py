"""Drop Cotacao.validade (campo morto) + CheckConstraint Rodada.status +
partial index RodadaProduto fila aprovacao pendente.

Revision ID: e9fa130602
Revises: d8e9fa130601
Create Date: 2026-04-24

Hygiene:
- validade nunca foi populado nem filtrado — campo morto.
- status: bloqueia INSERT/UPDATE com typo (ex: 'aberto' em vez de 'aberta').
- partial index: fila admin "aprovar produtos sugeridos" (aprovado IS NULL
  AND adicionado_por_fornecedor_id IS NOT NULL) é query quente.
"""
from alembic import op
import sqlalchemy as sa


revision = "e9fa130602"
down_revision = "d8e9fa130601"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop Cotacao.validade
    with op.batch_alter_table("cotacoes") as batch_op:
        batch_op.drop_column("validade")

    # 2. CheckConstraint em Rodada.status
    with op.batch_alter_table("rodadas") as batch_op:
        batch_op.create_check_constraint(
            "ck_rodada_status_valido",
            "status IN ('preparando','aguardando_cotacao','aberta',"
            "'em_negociacao','fechada','cotando','finalizada','cancelada')",
        )

    # 3. Partial index pra fila de aprovacao admin
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rodada_produto_aprovacao_pendente "
        "ON rodada_produtos (rodada_id) "
        "WHERE aprovado IS NULL AND adicionado_por_fornecedor_id IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_rodada_produto_aprovacao_pendente")

    with op.batch_alter_table("rodadas") as batch_op:
        batch_op.drop_constraint("ck_rodada_status_valido", type_="check")

    with op.batch_alter_table("cotacoes") as batch_op:
        batch_op.add_column(sa.Column("validade", sa.DateTime(timezone=True), nullable=True))
