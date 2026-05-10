"""audit_log

Tabela de auditoria estruturada (rastreabilidade administrativa).
Cobre o que EventoRodada nao cobre: login/logout, CRUD de leads,
produtos, lanchonetes, fornecedores, vendedores, mudancas de status
fora do fluxo de rodada.

Revision ID: l7g8h9i0j123
Revises: k6f7g8h9i012
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa


revision = "l7g8h9i0j123"
down_revision = "k6f7g8h9i012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", name="fk_audit_usuario"),
                  nullable=True),
        sa.Column("acao", sa.String(50), nullable=False),
        sa.Column("recurso_tipo", sa.String(40)),
        sa.Column("recurso_id", sa.Integer()),
        sa.Column("detalhes", sa.String(500)),
        sa.Column("ip", sa.String(45)),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_usuario_id", "audit_log", ["usuario_id"])
    op.create_index("ix_audit_log_acao", "audit_log", ["acao"])
    op.create_index("ix_audit_log_recurso_tipo", "audit_log", ["recurso_tipo"])
    op.create_index("ix_audit_log_criado_em", "audit_log", ["criado_em"])
    op.create_index("ix_audit_usuario_data", "audit_log", ["usuario_id", "criado_em"])


def downgrade():
    op.drop_index("ix_audit_usuario_data", table_name="audit_log")
    op.drop_index("ix_audit_log_criado_em", table_name="audit_log")
    op.drop_index("ix_audit_log_recurso_tipo", table_name="audit_log")
    op.drop_index("ix_audit_log_acao", table_name="audit_log")
    op.drop_index("ix_audit_log_usuario_id", table_name="audit_log")
    op.drop_table("audit_log")
