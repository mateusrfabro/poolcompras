# Helpers idempotentes para migrations Alembic.
#
# Motivacao: a baseline (86d17a406150) usa db.metadata.create_all(checkfirst=True),
# o que cria TODAS as tabelas do modelo final num DB Postgres/SQLite limpo. As
# migrations subsequentes, geradas por autogenerate, recriavam essas tabelas /
# colunas / indices e quebravam com "already exists" em DB limpo.
#
# Esses helpers usam SQLAlchemy Inspector (driver-agnostico) para checar
# existencia antes de cada DDL. Funciona em SQLite e Postgres sem mudanca.
#
# Uso tipico em uma migration:
#
#     from migrations._idempotent import has_column, has_index
#
#     def upgrade():
#         if not has_column('fornecedores', 'chave_pix'):
#             with op.batch_alter_table('fornecedores', schema=None) as batch_op:
#                 batch_op.add_column(sa.Column('chave_pix', sa.String(150)))
#
# Cuidado SQLite batch mode: ele recria a tabela inteira. Misturar ops ja
# aplicadas + ops novas dentro do mesmo `with batch_alter_table` em SQLite
# pode duplicar indices. Padrao seguro: um batch_alter_table por operacao
# (ou pular o batch inteiro se TODAS as ops dentro ja existem).

from alembic import op
from sqlalchemy import inspect


def _ins():
    return inspect(op.get_bind())


def has_table(name: str) -> bool:
    return name in _ins().get_table_names()


def has_column(table: str, column: str) -> bool:
    if not has_table(table):
        return False
    return column in {c["name"] for c in _ins().get_columns(table)}


def has_index(table: str, index_name: str) -> bool:
    if not has_table(table):
        return False
    return index_name in {ix["name"] for ix in _ins().get_indexes(table)}


def has_uq(table: str, name: str) -> bool:
    if not has_table(table):
        return False
    return name in {uq["name"] for uq in _ins().get_unique_constraints(table)}


def has_fk(table: str, name: str) -> bool:
    if not has_table(table):
        return False
    return name in {fk["name"] for fk in _ins().get_foreign_keys(table) if fk.get("name")}


def has_check(table: str, name: str) -> bool:
    if not has_table(table):
        return False
    try:
        constraints = _ins().get_check_constraints(table)
    except NotImplementedError:
        # Alguns dialetos podem nao implementar; assume ausencia.
        return False
    return name in {ck["name"] for ck in constraints if ck.get("name")}
