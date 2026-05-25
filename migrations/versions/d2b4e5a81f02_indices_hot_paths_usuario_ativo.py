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

Reescrita idempotente (2026-05): baseline cria coluna + indices via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column, has_index


revision = "d2b4e5a81f02"
down_revision = "c1f1a7e99001"
branch_labels = None
depends_on = None


def upgrade():
    # Usuario.ativo: add nullable + backfill + alter nullable=False
    if not has_column('usuarios', 'ativo'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.add_column(sa.Column("ativo", sa.Boolean(), nullable=True))
        # TRUE/FALSE em vez de 1/0: Postgres tem tipo BOOLEAN estrito.
        op.execute("UPDATE usuarios SET ativo = TRUE WHERE ativo IS NULL")
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.alter_column("ativo", nullable=False, server_default=sa.true())

    if not has_index('usuarios', 'ix_usuarios_ativo'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.create_index("ix_usuarios_ativo", ["ativo"])
    if not has_index('usuarios', 'ix_usuarios_tipo'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.create_index("ix_usuarios_tipo", ["tipo"])

    # Indices em FKs pra usuarios (um batch por op pra SQLite safety)
    for ix, cols in [
        ("ix_participacoes_rodada_pedido_aprovado_por_id", ["pedido_aprovado_por_id"]),
        ("ix_participacoes_rodada_pagamento_confirmado_por_id", ["pagamento_confirmado_por_id"]),
        ("ix_participacoes_rodada_entrega_informada_por_id", ["entrega_informada_por_id"]),
        ("ix_participacoes_rodada_aceite_proposta", ["aceite_proposta"]),
    ]:
        if not has_index('participacoes_rodada', ix):
            with op.batch_alter_table("participacoes_rodada") as batch_op:
                batch_op.create_index(ix, cols)

    if not has_index('eventos_rodada', 'ix_eventos_rodada_ator_id'):
        with op.batch_alter_table("eventos_rodada") as batch_op:
            batch_op.create_index("ix_eventos_rodada_ator_id", ["ator_id"])

    if not has_index('submissoes_cotacao', 'ix_submissoes_cotacao_aprovada_por_id'):
        with op.batch_alter_table("submissoes_cotacao") as batch_op:
            batch_op.create_index("ix_submissoes_cotacao_aprovada_por_id", ["aprovada_por_id"])

    if not has_index('notas_negociacao', 'ix_notas_negociacao_autor_usuario_id'):
        with op.batch_alter_table("notas_negociacao") as batch_op:
            batch_op.create_index("ix_notas_negociacao_autor_usuario_id", ["autor_usuario_id"])

    if not has_index('rodada_produtos', 'ix_rodada_produtos_adicionado_por_fornecedor_id'):
        with op.batch_alter_table("rodada_produtos") as batch_op:
            batch_op.create_index("ix_rodada_produtos_adicionado_por_fornecedor_id",
                                  ["adicionado_por_fornecedor_id"])

    if not has_index('rodadas', 'ix_rodadas_status'):
        with op.batch_alter_table("rodadas") as batch_op:
            batch_op.create_index("ix_rodadas_status", ["status"])

    if not has_index('cotacoes', 'ix_cotacoes_selecionada'):
        with op.batch_alter_table("cotacoes") as batch_op:
            batch_op.create_index("ix_cotacoes_selecionada", ["selecionada"])

    if not has_index('lanchonetes', 'ix_lanchonetes_ativa'):
        with op.batch_alter_table("lanchonetes") as batch_op:
            batch_op.create_index("ix_lanchonetes_ativa", ["ativa"])

    if not has_index('fornecedores', 'ix_fornecedores_ativo'):
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
        if has_index(tabela, ix):
            with op.batch_alter_table(tabela) as batch_op:
                batch_op.drop_index(ix)

    if has_index('usuarios', 'ix_usuarios_tipo'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.drop_index("ix_usuarios_tipo")
    if has_index('usuarios', 'ix_usuarios_ativo'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.drop_index("ix_usuarios_ativo")
    if has_column('usuarios', 'ativo'):
        with op.batch_alter_table("usuarios") as batch_op:
            batch_op.drop_column("ativo")
