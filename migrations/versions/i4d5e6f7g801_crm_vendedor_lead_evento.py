"""crm_vendedor_lead_evento

Cria tabelas vendedores, leads, lead_eventos. Adiciona vendedor_id em
lanchonetes e fornecedores (FK opcional pra atribuir SDR responsavel).

Revision ID: i4d5e6f7g801
Revises: h3c4d5e6f701
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa


revision = "i4d5e6f7g801"
down_revision = "h3c4d5e6f701"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vendedores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("meta_mensal_clientes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"],
                                name="fk_vendedores_usuario_id"),
        sa.UniqueConstraint("usuario_id", name="uq_vendedores_usuario_id"),
        sa.CheckConstraint("meta_mensal_clientes > 0",
                           name="ck_vendedor_meta_positiva"),
    )
    op.create_index("ix_vendedores_ativo", "vendedores", ["ativo"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome_estabelecimento", sa.String(150), nullable=False),
        sa.Column("nome_contato", sa.String(100)),
        sa.Column("telefone", sa.String(20)),
        sa.Column("email", sa.String(120)),
        sa.Column("cidade", sa.String(80)),
        sa.Column("cnpj", sa.String(18)),
        sa.Column("observacoes", sa.String(500)),
        sa.Column("vendedor_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="frio"),
        sa.Column("lanchonete_id", sa.Integer(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizado_em", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["vendedor_id"], ["vendedores.id"],
                                name="fk_leads_vendedor_id"),
        sa.ForeignKeyConstraint(["lanchonete_id"], ["lanchonetes.id"],
                                name="fk_leads_lanchonete_id"),
        sa.UniqueConstraint("lanchonete_id", name="uq_leads_lanchonete_id"),
        sa.CheckConstraint(
            "status IN ('frio','morno','quente','fechado','cancelado')",
            name="ck_lead_status_valido",
        ),
    )
    op.create_index("ix_leads_vendedor_id", "leads", ["vendedor_id"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_lanchonete_id", "leads", ["lanchonete_id"])
    op.create_index("ix_leads_criado_em", "leads", ["criado_em"])
    op.create_index("ix_lead_vendedor_status_atualizado",
                    "leads", ["vendedor_id", "status", "atualizado_em"])

    op.create_table(
        "lead_eventos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("autor_usuario_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False, server_default="nota"),
        sa.Column("descricao", sa.String(1000), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"],
                                name="fk_lead_eventos_lead_id"),
        sa.ForeignKeyConstraint(["autor_usuario_id"], ["usuarios.id"],
                                name="fk_lead_eventos_autor_id"),
    )
    op.create_index("ix_lead_eventos_lead_id", "lead_eventos", ["lead_id"])
    op.create_index("ix_lead_eventos_autor_id", "lead_eventos",
                    ["autor_usuario_id"])
    op.create_index("ix_lead_eventos_criado_em", "lead_eventos", ["criado_em"])

    # vendedor_id em lanchonetes + fornecedores
    with op.batch_alter_table("lanchonetes") as batch_op:
        batch_op.add_column(sa.Column("vendedor_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_lanchonetes_vendedor_id", "vendedores",
            ["vendedor_id"], ["id"],
        )
        batch_op.create_index("ix_lanchonetes_vendedor_id", ["vendedor_id"])

    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.add_column(sa.Column("vendedor_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_fornecedores_vendedor_id", "vendedores",
            ["vendedor_id"], ["id"],
        )
        batch_op.create_index("ix_fornecedores_vendedor_id", ["vendedor_id"])


def downgrade():
    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.drop_index("ix_fornecedores_vendedor_id")
        batch_op.drop_constraint("fk_fornecedores_vendedor_id", type_="foreignkey")
        batch_op.drop_column("vendedor_id")

    with op.batch_alter_table("lanchonetes") as batch_op:
        batch_op.drop_index("ix_lanchonetes_vendedor_id")
        batch_op.drop_constraint("fk_lanchonetes_vendedor_id", type_="foreignkey")
        batch_op.drop_column("vendedor_id")

    op.drop_index("ix_lead_eventos_criado_em", table_name="lead_eventos")
    op.drop_index("ix_lead_eventos_autor_id", table_name="lead_eventos")
    op.drop_index("ix_lead_eventos_lead_id", table_name="lead_eventos")
    op.drop_table("lead_eventos")

    op.drop_index("ix_lead_vendedor_status_atualizado", table_name="leads")
    op.drop_index("ix_leads_criado_em", table_name="leads")
    op.drop_index("ix_leads_lanchonete_id", table_name="leads")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_vendedor_id", table_name="leads")
    op.drop_table("leads")

    op.drop_index("ix_vendedores_ativo", table_name="vendedores")
    op.drop_table("vendedores")
