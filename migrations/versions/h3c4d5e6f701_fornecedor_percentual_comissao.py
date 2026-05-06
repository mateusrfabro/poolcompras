"""fornecedor_percentual_comissao

Adiciona Fornecedor.percentual_comissao (Numeric(5,2), default=0) com
CHECK constraint 0 <= % <= 100. Suporta o modulo de comissao introduzido
no roadmap pos-deploy: admin define o % por fornecedor e o sistema
agrega vendas efetivadas dia a dia pra mostrar o que o fornecedor deve
pagar pra Aggron.

Default 0 = fornecedores legacy continuam ativos sem cobrar comissao
ate o admin definir um %.

Revision ID: h3c4d5e6f701
Revises: g2b3c4d5e601
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa


revision = "h3c4d5e6f701"
down_revision = "g2b3c4d5e601"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.add_column(sa.Column(
            "percentual_comissao",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="0",
        ))
        batch_op.create_check_constraint(
            "ck_fornecedor_comissao_pct",
            "percentual_comissao >= 0 AND percentual_comissao <= 100",
        )


def downgrade():
    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.drop_constraint("ck_fornecedor_comissao_pct", type_="check")
        batch_op.drop_column("percentual_comissao")
