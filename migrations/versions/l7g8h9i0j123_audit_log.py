"""audit_log

Tabela de auditoria estruturada (rastreabilidade administrativa).
Cobre o que EventoRodada nao cobre: login/logout, CRUD de leads,
produtos, lanchonetes, fornecedores, vendedores, mudancas de status
fora do fluxo de rodada.

Revision ID: l7g8h9i0j123
Revises: k6f7g8h9i012
Create Date: 2026-05-10

Reescrita idempotente (2026-05): baseline cria tabela/indices via metadata.
"""
from alembic import op
import sqlalchemy as sa

from migrations._idempotent import has_index, has_table


revision = "l7g8h9i0j123"
down_revision = "k6f7g8h9i012"
branch_labels = None
depends_on = None


def upgrade():
    if not has_table('audit_log'):
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
    for ix, cols in [
        ("ix_audit_log_usuario_id", ["usuario_id"]),
        ("ix_audit_log_acao", ["acao"]),
        ("ix_audit_log_recurso_tipo", ["recurso_tipo"]),
        ("ix_audit_log_criado_em", ["criado_em"]),
        ("ix_audit_usuario_data", ["usuario_id", "criado_em"]),
    ]:
        if not has_index('audit_log', ix):
            op.create_index(ix, "audit_log", cols)


def downgrade():
    for ix in ("ix_audit_usuario_data", "ix_audit_log_criado_em",
               "ix_audit_log_recurso_tipo", "ix_audit_log_acao",
               "ix_audit_log_usuario_id"):
        if has_index('audit_log', ix):
            op.drop_index(ix, table_name="audit_log")
    if has_table('audit_log'):
        op.drop_table("audit_log")
