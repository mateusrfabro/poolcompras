"""recusa_fornecedor — aceite parcial por fornecedor

Tabela de recusas: lanchonete aceita a proposta mas recusa fornecedor X.
Ausencia de linha = fornecedor aceito (quando ParticipacaoRodada.aceite_proposta=True).

Decisao Mateus 2026-05-28 — opcao MINI: aceite parcial sem refactor profundo do
fluxo (comprovante e recebimento seguem unicos; so calculos financeiros e
fluxo do fornecedor filtram recusados).

Revision ID: m8h9i0j1k234
Revises: l7g8h9i0j123
Create Date: 2026-05-28

Idempotente (segue padrao do projeto pos baseline 86d17a406150).
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_index, has_table, has_uq


revision = "m8h9i0j1k234"
down_revision = "l7g8h9i0j123"
branch_labels = None
depends_on = None


def upgrade():
    if not has_table("recusas_fornecedor"):
        op.create_table(
            "recusas_fornecedor",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rodada_id", sa.Integer(),
                      sa.ForeignKey("rodadas.id", name="fk_recusa_rodada"),
                      nullable=False),
            sa.Column("lanchonete_id", sa.Integer(),
                      sa.ForeignKey("lanchonetes.id", name="fk_recusa_lanchonete"),
                      nullable=False),
            sa.Column("fornecedor_id", sa.Integer(),
                      sa.ForeignKey("fornecedores.id", name="fk_recusa_fornecedor"),
                      nullable=False),
            sa.Column("motivo", sa.String(500)),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
        )

    for ix, cols in [
        ("ix_recusas_fornecedor_rodada_id", ["rodada_id"]),
        ("ix_recusas_fornecedor_lanchonete_id", ["lanchonete_id"]),
        ("ix_recusas_fornecedor_fornecedor_id", ["fornecedor_id"]),
    ]:
        if not has_index("recusas_fornecedor", ix):
            op.create_index(ix, "recusas_fornecedor", cols)

    if not has_uq("recusas_fornecedor", "uq_recusa_rodada_lanch_forn"):
        # SQLite nao suporta ADD CONSTRAINT — usar batch_alter_table.
        with op.batch_alter_table("recusas_fornecedor", schema=None) as batch_op:
            batch_op.create_unique_constraint(
                "uq_recusa_rodada_lanch_forn",
                ["rodada_id", "lanchonete_id", "fornecedor_id"],
            )


def downgrade():
    for ix in ("ix_recusas_fornecedor_fornecedor_id",
               "ix_recusas_fornecedor_lanchonete_id",
               "ix_recusas_fornecedor_rodada_id"):
        if has_index("recusas_fornecedor", ix):
            op.drop_index(ix, table_name="recusas_fornecedor")
    if has_table("recusas_fornecedor"):
        op.drop_table("recusas_fornecedor")
