"""Postgres-only: TIMESTAMPTZ em todas colunas datetime + unique partial em cotacoes.

Revision ID: a5b6c7d8e903
Revises: f4a2c9d81b05
Create Date: 2026-04-23

SQLite: no-op (DateTime(timezone=True) so afeta binding Python; SQLite retorna naive).
Postgres: ALTER COLUMN TYPE TIMESTAMPTZ USING col AT TIME ZONE 'UTC' + CREATE UNIQUE INDEX partial.
"""
from alembic import op


revision = "a5b6c7d8e903"
down_revision = "f4a2c9d81b05"
branch_labels = None
depends_on = None


# (tabela, coluna) pra cada db.DateTime(timezone=True) do schema.
COLUNAS_TEMPORAIS = [
    ("usuarios", "criado_em"),
    ("usuarios", "senha_atualizada_em"),
    ("lanchonetes", "criado_em"),
    ("produtos", "criado_em"),
    ("rodadas", "data_abertura"),
    ("rodadas", "data_fechamento"),
    ("rodadas", "criado_em"),
    ("rodadas", "deadline_pedido"),
    ("rodadas", "deadline_cotacao"),
    ("rodadas", "deadline_aceite"),
    ("rodadas", "deadline_pagamento"),
    ("rodadas", "deadline_entrega"),
    ("rodadas", "deadline_confirmacao"),
    ("itens_pedido", "criado_em"),
    ("fornecedores", "criado_em"),
    ("cotacoes", "validade"),
    ("cotacoes", "criado_em"),
    ("participacoes_rodada", "pedido_enviado_em"),
    ("participacoes_rodada", "pedido_aprovado_em"),
    ("participacoes_rodada", "pedido_devolvido_em"),
    ("participacoes_rodada", "pedido_reprovado_em"),
    ("participacoes_rodada", "aceite_em"),
    ("participacoes_rodada", "comprovante_em"),
    ("participacoes_rodada", "pagamento_confirmado_em"),
    ("participacoes_rodada", "entrega_informada_em"),
    ("participacoes_rodada", "recebimento_em"),
    ("participacoes_rodada", "avaliacao_em"),
    ("participacoes_rodada", "criado_em"),
    ("avaliacoes_rodada", "criado_em"),
    ("eventos_rodada", "criado_em"),
    ("rodada_produtos", "criado_em"),
    ("submissoes_cotacao", "enviada_em"),
    ("submissoes_cotacao", "aprovada_em"),
    ("submissoes_cotacao", "devolvida_em"),
    ("submissoes_cotacao", "criado_em"),
    ("notas_negociacao", "criado_em"),
]


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite: no-op

    for tabela, coluna in COLUNAS_TEMPORAIS:
        op.execute(
            f'ALTER TABLE {tabela} '
            f'ALTER COLUMN {coluna} TYPE TIMESTAMPTZ '
            f'USING {coluna} AT TIME ZONE \'UTC\''
        )

    # Unique partial: no maximo 1 vencedora por (rodada, produto).
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_cotacao_vencedora_unica '
        'ON cotacoes (rodada_id, produto_id) WHERE selecionada IS TRUE'
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute('DROP INDEX IF EXISTS ix_cotacao_vencedora_unica')

    for tabela, coluna in COLUNAS_TEMPORAIS:
        op.execute(
            f'ALTER TABLE {tabela} '
            f'ALTER COLUMN {coluna} TYPE TIMESTAMP'
        )
