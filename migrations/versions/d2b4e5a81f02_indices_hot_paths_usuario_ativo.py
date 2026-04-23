"""indices_hot_paths_usuario_ativo

Adiciona:
- Usuario.ativo (default True, nullable False)
- Indices em FKs ausentes (participacoes_rodada.pedido_aprovado_por_id,
  pagamento_confirmado_por_id, entrega_informada_por_id,
  eventos_rodada.ator_id, submissoes_cotacao.aprovada_por_id,
  notas_negociacao.autor_usuario_id, rodada_produtos.adicionado_por_fornecedor_id).
- Indices em colunas filtradas quentes: rodadas.status, cotacoes.selecionada,
  participacoes_rodada.aceite_proposta, lanchonetes.ativa, fornecedores.ativo,
  usuarios.tipo, usuarios.ativo.

Revision ID: d2b4e5a81f02
Revises: c1f1a7e99001
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa


revision = "d2b4e5a81f02"
down_revision = "c1f1a7e99001"
branch_labels = None
depends_on = None


def upgrade():
    # Usuario.ativo (default True pra nao travar usuarios existentes)
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(sa.Column("ativo", sa.Boolean(), nullable=True))
    op.execute("UPDATE usuarios SET ativo = 1 WHERE ativo IS NULL")
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.alter_column("ativo", nullable=False, server_default=sa.true())
        batch_op.create_index("ix_usuarios_ativo", ["ativo"])
        batch_op.create_index("ix_usuarios_tipo", ["tipo"])

    # Indices em FKs pra usuarios
    with op.batch_alter_table("participacoes_rodada") as batch_op:
        batch_op.create_index("ix_participacoes_rodada_pedido_aprovado_por_id",
                              ["pedido_aprovado_por_id"])
        batch_op.create_index("ix_participacoes_rodada_pagamento_confirmado_por_id",
                              ["pagamento_confirmado_por_id"])
        batch_op.create_index("ix_participacoes_rodada_entrega_informada_por_id",
                              ["entrega_informada_por_id"])
        batch_op.create_index("ix_participacoes_rodada_aceite_proposta",
                              ["aceite_proposta"])

    with op.batch_alter_table("eventos_rodada") as batch_op:
        batch_op.create_index("ix_eventos_rodada_ator_id", ["ator_id"])

    with op.batch_alter_table("submissoes_cotacao") as batch_op:
        batch_op.create_index("ix_submissoes_cotacao_aprovada_por_id",
                              ["aprovada_por_id"])

    with op.batch_alter_table("notas_negociacao") as batch_op:
        batch_op.create_index("ix_notas_negociacao_autor_usuario_id",
                              ["autor_usuario_id"])

    with op.batch_alter_table("rodada_produtos") as batch_op:
        batch_op.create_index("ix_rodada_produtos_adicionado_por_fornecedor_id",
                              ["adicionado_por_fornecedor_id"])

    # Indices em colunas filtradas
    with op.batch_alter_table("rodadas") as batch_op:
        batch_op.create_index("ix_rodadas_status", ["status"])

    with op.batch_alter_table("cotacoes") as batch_op:
        batch_op.create_index("ix_cotacoes_selecionada", ["selecionada"])

    with op.batch_alter_table("lanchonetes") as batch_op:
        batch_op.create_index("ix_lanchonetes_ativa", ["ativa"])

    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.create_index("ix_fornecedores_ativo", ["ativo"])


def downgrade():
    for ix, tabela in [
        ("ix_fornecedores_ativo", "fornecedores"),
        ("ix_lanchonetes_ativa", "lanchonetes"),
        ("ix_cotacoes_selecionada", "cotacoes"),
        ("ix_rodadas_status", "rodadas"),
        ("ix_rodada_produtos_adicionado_por_fornecedor_id", "rodada_produtos"),
        ("ix_notas_negociacao_autor_usuario_id", "notas_negociacao"),
        ("ix_submissoes_cotacao_aprovada_por_id", "submissoes_cotacao"),
        ("ix_eventos_rodada_ator_id", "eventos_rodada"),
        ("ix_participacoes_rodada_aceite_proposta", "participacoes_rodada"),
        ("ix_participacoes_rodada_entrega_informada_por_id", "participacoes_rodada"),
        ("ix_participacoes_rodada_pagamento_confirmado_por_id", "participacoes_rodada"),
        ("ix_participacoes_rodada_pedido_aprovado_por_id", "participacoes_rodada"),
    ]:
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.drop_index(ix)

    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_index("ix_usuarios_tipo")
        batch_op.drop_index("ix_usuarios_ativo")
        batch_op.drop_column("ativo")
