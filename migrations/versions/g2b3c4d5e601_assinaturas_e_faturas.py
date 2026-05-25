"""assinaturas_e_faturas

Cria tabelas Assinatura (1 contrato anual por lanchonete) e Fatura
(parcelas mensais — 12 por contrato no MVP). Suporta a area financeira
introduzida no roadmap pos-deploy:
- Admin marca pagamento de mensalidade + sobe PDF da NF.
- Lanchonete ve vigencia + 12 parcelas + status + download da NF.

NF emitida fora do sistema (no MVP): admin sobe PDF manual em
fatura.nf_pdf_key. Integracao automatica (NFe.io/Notazz) fica pra v2.

Revision ID: g2b3c4d5e601
Revises: f1a2b3c4d501
Create Date: 2026-05-06

Reescrita idempotente (2026-05): baseline cria tabelas/indices via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_index, has_table


revision = "g2b3c4d5e601"
down_revision = "f1a2b3c4d501"
branch_labels = None
depends_on = None


def upgrade():
    if not has_table('assinaturas'):
        op.create_table(
            "assinaturas",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("lanchonete_id", sa.Integer(), nullable=False),
            sa.Column("valor_mensal", sa.Numeric(12, 2), nullable=False),
            sa.Column("parcelas_total", sa.Integer(), nullable=False, server_default="12"),
            sa.Column("vigencia_inicio", sa.Date(), nullable=False),
            sa.Column("vigencia_fim", sa.Date(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="ativa"),
            sa.Column(
                "criado_em",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(
                ["lanchonete_id"], ["lanchonetes.id"],
                name="fk_assinaturas_lanchonete_id",
            ),
            sa.CheckConstraint(
                "status IN ('ativa','suspensa','cancelada','encerrada')",
                name="ck_assinatura_status_valido",
            ),
            sa.CheckConstraint("valor_mensal > 0", name="ck_assinatura_valor_positivo"),
            sa.CheckConstraint(
                "parcelas_total BETWEEN 1 AND 24",
                name="ck_assinatura_parcelas_range",
            ),
            sa.CheckConstraint(
                "vigencia_fim >= vigencia_inicio",
                name="ck_assinatura_vigencia_ordem",
            ),
        )
    if not has_index('assinaturas', 'ix_assinaturas_lanchonete_id'):
        op.create_index("ix_assinaturas_lanchonete_id", "assinaturas", ["lanchonete_id"])
    if not has_index('assinaturas', 'ix_assinaturas_status'):
        op.create_index("ix_assinaturas_status", "assinaturas", ["status"])

    if not has_table('faturas'):
        op.create_table(
            "faturas",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("assinatura_id", sa.Integer(), nullable=False),
            sa.Column("parcela_numero", sa.Integer(), nullable=False),
            sa.Column("mes_referencia", sa.Date(), nullable=False),
            sa.Column("valor", sa.Numeric(12, 2), nullable=False),
            sa.Column("vencimento", sa.Date(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
            sa.Column("pago_em", sa.DateTime(timezone=True), nullable=True),
            sa.Column("pago_por_id", sa.Integer(), nullable=True),
            sa.Column("nf_pdf_key", sa.String(255), nullable=True),
            sa.Column("nf_emitida_em", sa.DateTime(timezone=True), nullable=True),
            sa.Column("observacao", sa.String(500), nullable=True),
            sa.Column(
                "criado_em",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(
                ["assinatura_id"], ["assinaturas.id"],
                name="fk_faturas_assinatura_id",
            ),
            sa.ForeignKeyConstraint(
                ["pago_por_id"], ["usuarios.id"],
                name="fk_faturas_pago_por_id",
            ),
            sa.UniqueConstraint(
                "assinatura_id", "parcela_numero",
                name="uq_fatura_assinatura_parcela",
            ),
            sa.CheckConstraint(
                "status IN ('pendente','paga','atrasada','cancelada')",
                name="ck_fatura_status_valido",
            ),
            sa.CheckConstraint("valor > 0", name="ck_fatura_valor_positivo"),
            sa.CheckConstraint(
                "parcela_numero BETWEEN 1 AND 24",
                name="ck_fatura_parcela_range",
            ),
        )
    for ix, cols in [
        ("ix_faturas_assinatura_id", ["assinatura_id"]),
        ("ix_faturas_mes_referencia", ["mes_referencia"]),
        ("ix_faturas_vencimento", ["vencimento"]),
        ("ix_faturas_status", ["status"]),
        ("ix_faturas_pago_por_id", ["pago_por_id"]),
        ("ix_fatura_status_vencimento", ["status", "vencimento"]),
    ]:
        if not has_index('faturas', ix):
            op.create_index(ix, "faturas", cols)


def downgrade():
    for ix in ("ix_fatura_status_vencimento", "ix_faturas_pago_por_id",
               "ix_faturas_status", "ix_faturas_vencimento",
               "ix_faturas_mes_referencia", "ix_faturas_assinatura_id"):
        if has_index('faturas', ix):
            op.drop_index(ix, table_name="faturas")
    if has_table('faturas'):
        op.drop_table("faturas")

    for ix in ("ix_assinaturas_status", "ix_assinaturas_lanchonete_id"):
        if has_index('assinaturas', ix):
            op.drop_index(ix, table_name="assinaturas")
    if has_table('assinaturas'):
        op.drop_table("assinaturas")
