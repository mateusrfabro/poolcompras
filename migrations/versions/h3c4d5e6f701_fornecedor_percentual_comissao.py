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

Reescrita idempotente (2026-05): baseline cria coluna/check via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_check, has_column


revision = "h3c4d5e6f701"
down_revision = "g2b3c4d5e601"
branch_labels = None
depends_on = None


def upgrade():
    if not has_column('fornecedores', 'percentual_comissao'):
        with op.batch_alter_table("fornecedores") as batch_op:
            batch_op.add_column(sa.Column(
                "percentual_comissao",
                sa.Numeric(5, 2),
                nullable=False,
                server_default="0",
            ))
    if not has_check('fornecedores', 'ck_fornecedor_comissao_pct'):
        with op.batch_alter_table("fornecedores") as batch_op:
            batch_op.create_check_constraint(
                "ck_fornecedor_comissao_pct",
                "percentual_comissao >= 0 AND percentual_comissao <= 100",
            )


def downgrade():
    if has_check('fornecedores', 'ck_fornecedor_comissao_pct'):
        with op.batch_alter_table("fornecedores") as batch_op:
            batch_op.drop_constraint("ck_fornecedor_comissao_pct", type_="check")
    if has_column('fornecedores', 'percentual_comissao'):
        with op.batch_alter_table("fornecedores") as batch_op:
            batch_op.drop_column("percentual_comissao")
