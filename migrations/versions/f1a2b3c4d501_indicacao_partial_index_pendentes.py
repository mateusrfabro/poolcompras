"""indicacao_partial_index_pendentes

Partial index em indicacoes(indicador_lanchonete_id, criado_em) WHERE
recompensa_aplicada_em IS NULL. Acelera as 4 queries hot do dashboard:
- calcular_status_recompensa (elegiveis + aguardando)
- _notificar_quase_la_se_aplicavel
- resgatar_recompensa (FIFO com FOR UPDATE)
- indicacoes_da_lanchonete (list view)

`CREATE INDEX ... WHERE` eh portavel entre Postgres e SQLite (ambos suportam
desde versoes antigas). op.execute() em vez de batch_op.create_index pra
nao depender de kwargs especificos do dialect dentro do batch.

Revision ID: f1a2b3c4d501
Revises: b7d8e9fa1301
Create Date: 2026-05-04
"""
from alembic import op


revision = "f1a2b3c4d501"
down_revision = "b7d8e9fa1301"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX ix_indicacao_pendentes "
        "ON indicacoes (indicador_lanchonete_id, criado_em) "
        "WHERE recompensa_aplicada_em IS NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_indicacao_pendentes")
