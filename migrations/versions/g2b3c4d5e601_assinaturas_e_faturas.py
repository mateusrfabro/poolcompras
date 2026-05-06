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
"""
from alembic import op
import sqlalchemy as sa


revision = "g2b3c4d5e601"
down_revision = "f1a2b3c4d501"
branch_labels = None
depends_on = None


def upgrade():
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
    op.create_index("ix_assinaturas_lanchonete_id", "assinaturas", ["lanchonete_id"])
    op.create_index("ix_assinaturas_status", "assinaturas", ["status"])

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
    op.create_index("ix_faturas_assinatura_id", "faturas", ["assinatura_id"])
    op.create_index("ix_faturas_mes_referencia", "faturas", ["mes_referencia"])
    op.create_index("ix_faturas_vencimento", "faturas", ["vencimento"])
    op.create_index("ix_faturas_status", "faturas", ["status"])
    op.create_index("ix_faturas_pago_por_id", "faturas", ["pago_por_id"])
    op.create_index("ix_fatura_status_vencimento", "faturas", ["status", "vencimento"])


def downgrade():
    op.drop_index("ix_fatura_status_vencimento", table_name="faturas")
    op.drop_index("ix_faturas_pago_por_id", table_name="faturas")
    op.drop_index("ix_faturas_status", table_name="faturas")
    op.drop_index("ix_faturas_vencimento", table_name="faturas")
    op.drop_index("ix_faturas_mes_referencia", table_name="faturas")
    op.drop_index("ix_faturas_assinatura_id", table_name="faturas")
    op.drop_table("faturas")

    op.drop_index("ix_assinaturas_status", table_name="assinaturas")
    op.drop_index("ix_assinaturas_lanchonete_id", table_name="assinaturas")
    op.drop_table("assinaturas")
