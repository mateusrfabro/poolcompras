"""indices_perf_dashboard

Indices de performance identificados em auditoria:
- produtos.ativo: filtrado em ~6 rotas (catalogo admin, KPI, dashboard
  fornecedor) com WHERE ativo=True. Postgres em prod fazia seq scan.
- rodadas.data_abertura: usado em ORDER BY em ~6 rotas (listagens).
- rodada_produtos.criado_em: usado em ORDER BY do export historico_aprovacoes.

Revision ID: j5e6f7g8h901
Revises: i4d5e6f7g801
Create Date: 2026-05-09

Reescrita idempotente (2026-05): baseline cria indices via metadata.
"""
from alembic import op

from migrations._idempotent import has_index


revision = "j5e6f7g8h901"
down_revision = "i4d5e6f7g801"
branch_labels = None
depends_on = None


def upgrade():
    if not has_index('produtos', 'ix_produtos_ativo'):
        op.create_index("ix_produtos_ativo", "produtos", ["ativo"])
    if not has_index('rodadas', 'ix_rodadas_data_abertura'):
        op.create_index("ix_rodadas_data_abertura", "rodadas", ["data_abertura"])
    if not has_index('rodada_produtos', 'ix_rodada_produtos_criado_em'):
        op.create_index("ix_rodada_produtos_criado_em", "rodada_produtos", ["criado_em"])


def downgrade():
    if has_index('rodada_produtos', 'ix_rodada_produtos_criado_em'):
        op.drop_index("ix_rodada_produtos_criado_em", table_name="rodada_produtos")
    if has_index('rodadas', 'ix_rodadas_data_abertura'):
        op.drop_index("ix_rodadas_data_abertura", table_name="rodadas")
    if has_index('produtos', 'ix_produtos_ativo'):
        op.drop_index("ix_produtos_ativo", table_name="produtos")
