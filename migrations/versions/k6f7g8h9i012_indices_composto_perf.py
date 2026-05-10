"""indices_composto_perf

Indices compostos identificados em re-audit DB:
- rodada_produtos (rodada_id, aprovado): catalogo de rodada filtra hot
  por aprovacao (None | True) — sem composto eh seq scan.
- participacoes_rodada (rodada_id, aceite_proposta): pendencias_fornecedor
  + funil de aceite filtram por essa combinacao.

Revision ID: k6f7g8h9i012
Revises: j5e6f7g8h901
Create Date: 2026-05-10
"""
from alembic import op


revision = "k6f7g8h9i012"
down_revision = "j5e6f7g8h901"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_rodada_produtos_rodada_aprovado",
        "rodada_produtos",
        ["rodada_id", "aprovado"],
    )
    op.create_index(
        "ix_participacao_rodada_aceite",
        "participacoes_rodada",
        ["rodada_id", "aceite_proposta"],
    )


def downgrade():
    op.drop_index(
        "ix_participacao_rodada_aceite",
        table_name="participacoes_rodada",
    )
    op.drop_index(
        "ix_rodada_produtos_rodada_aprovado",
        table_name="rodada_produtos",
    )
