"""indices_perf_dashboard

Indices de performance identificados em auditoria:
- produtos.ativo: filtrado em ~6 rotas (catalogo admin, KPI, dashboard
  fornecedor) com WHERE ativo=True. Postgres em prod fazia seq scan.
- rodadas.data_abertura: usado em ORDER BY em ~6 rotas (listagens).
- rodada_produtos.criado_em: usado em ORDER BY do export historico_aprovacoes.

Revision ID: j5e6f7g8h901
Revises: i4d5e6f7g801
Create Date: 2026-05-09
"""
from alembic import op


revision = "j5e6f7g8h901"
down_revision = "i4d5e6f7g801"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_produtos_ativo", "produtos", ["ativo"])
    op.create_index("ix_rodadas_data_abertura", "rodadas", ["data_abertura"])
    op.create_index("ix_rodada_produtos_criado_em", "rodada_produtos", ["criado_em"])


def downgrade():
    op.drop_index("ix_rodada_produtos_criado_em", table_name="rodada_produtos")
    op.drop_index("ix_rodadas_data_abertura", table_name="rodadas")
    op.drop_index("ix_produtos_ativo", table_name="produtos")
