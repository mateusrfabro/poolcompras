"""Programa de indicacao: lanchonete.codigo_indicacao + tabela indicacoes

Revision ID: b7d8e9fa1301
Revises: a1b2c3d4e5f6
Create Date: 2026-05-03

MVP do programa "indique e ganhe": cada lanchonete recebe codigo unico
pra espalhar (link aggron.com.br/registro?ind=ABC123). Apos 3 indicadas
ativas ha 30 dias, indicadora ganha 1 mes gratis (aplicado manualmente
pela equipe via notif Telegram).

Reescrita idempotente (2026-05): baseline cria coluna/tabela via metadata.
Backfill so roda se houver registros com codigo_indicacao IS NULL.
"""
import secrets

from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_column, has_index, has_table


revision = "b7d8e9fa1301"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


# Alfabeto sem caracteres confusos (sem 0/O/1/I/L) — copy-paste manual fica
# resistente a leitura ambigua quando lanchonete dita codigo por telefone.
_ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_codigo(rng=None):
    rng = rng or secrets
    return "".join(rng.choice(_ALPHA) for _ in range(8))


def upgrade():
    # 1) Adiciona codigo_indicacao em lanchonetes (nullable inicialmente
    # pra preservar legacy; service gera lazy no primeiro acesso).
    if not has_column('lanchonetes', 'codigo_indicacao'):
        with op.batch_alter_table("lanchonetes") as batch_op:
            batch_op.add_column(
                sa.Column("codigo_indicacao", sa.String(length=8), nullable=True)
            )
    if not has_index('lanchonetes', 'ix_lanchonetes_codigo_indicacao'):
        with op.batch_alter_table("lanchonetes") as batch_op:
            batch_op.create_index(
                "ix_lanchonetes_codigo_indicacao",
                ["codigo_indicacao"], unique=True,
            )

    # 2) Backfill: gera codigo unico pra cada lanchonete sem codigo.
    # Idempotente — so atua em rows com codigo NULL.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id FROM lanchonetes WHERE codigo_indicacao IS NULL"
    )).fetchall()
    usados = set()
    for (lanch_id,) in rows:
        # Loop ate achar codigo unico (chance de colisao desprezivel — 31^8 ~ 8.5e11
        # entradas possiveis, alfabeto sem 0/O/1/I/L; mas blindamos com check).
        for _ in range(20):
            cod = _gen_codigo()
            if cod in usados:
                continue
            existe = conn.execute(sa.text(
                "SELECT 1 FROM lanchonetes WHERE codigo_indicacao = :c"
            ), {"c": cod}).fetchone()
            if not existe:
                conn.execute(sa.text(
                    "UPDATE lanchonetes SET codigo_indicacao = :c WHERE id = :i"
                ), {"c": cod, "i": lanch_id})
                usados.add(cod)
                break
        else:
            # Quebra explicita > linha sem codigo. 20 colisoes em 8.5e11 = bug.
            raise RuntimeError(
                f"falha ao gerar codigo unico de indicacao pra lanchonete {lanch_id} "
                f"apos 20 tentativas — investigar RNG/seed"
            )

    # 3) Cria tabela indicacoes.
    if not has_table('indicacoes'):
        op.create_table(
            "indicacoes",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("indicador_lanchonete_id", sa.Integer, nullable=False),
            sa.Column("indicada_lanchonete_id", sa.Integer, nullable=False),
            sa.Column("codigo_usado", sa.String(length=8), nullable=False),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("recompensa_aplicada_em", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["indicador_lanchonete_id"], ["lanchonetes.id"],
                name="fk_indicacao_indicador",
            ),
            sa.ForeignKeyConstraint(
                ["indicada_lanchonete_id"], ["lanchonetes.id"],
                name="fk_indicacao_indicada",
            ),
            sa.UniqueConstraint(
                "indicada_lanchonete_id", name="uq_indicacao_indicada",
            ),
            sa.CheckConstraint(
                "indicador_lanchonete_id <> indicada_lanchonete_id",
                name="ck_indicacao_nao_propria",
            ),
        )
    if not has_index('indicacoes', 'ix_indicacoes_indicador_lanchonete_id'):
        op.create_index(
            "ix_indicacoes_indicador_lanchonete_id",
            "indicacoes", ["indicador_lanchonete_id"],
        )
    if not has_index('indicacoes', 'ix_indicacoes_criado_em'):
        op.create_index(
            "ix_indicacoes_criado_em",
            "indicacoes", ["criado_em"],
        )


def downgrade():
    if has_index('indicacoes', 'ix_indicacoes_criado_em'):
        op.drop_index("ix_indicacoes_criado_em", table_name="indicacoes")
    if has_index('indicacoes', 'ix_indicacoes_indicador_lanchonete_id'):
        op.drop_index("ix_indicacoes_indicador_lanchonete_id", table_name="indicacoes")
    if has_table('indicacoes'):
        op.drop_table("indicacoes")
    if has_index('lanchonetes', 'ix_lanchonetes_codigo_indicacao'):
        with op.batch_alter_table("lanchonetes") as batch_op:
            batch_op.drop_index("ix_lanchonetes_codigo_indicacao")
    if has_column('lanchonetes', 'codigo_indicacao'):
        with op.batch_alter_table("lanchonetes") as batch_op:
            batch_op.drop_column("codigo_indicacao")
