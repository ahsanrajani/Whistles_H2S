"""Idempotent versions of the Alembic operations that create objects.

``0001_baseline`` builds the schema from the *current* models (``Base.metadata.create_all``), so on a fresh
database every column, table and index that a later revision adds already exists by the time that revision
runs. Revisions 0034-0039 therefore used to fail with "already exists" on any new database (local, CI or
Cloud SQL). On an older database, which really is missing those objects, they still get created.

Each helper checks the live schema first and does nothing if the object is present. They exist only for
revisions written after the baseline was generated from models; new revisions should not need them.
"""
import sqlalchemy as sa
from alembic import op


def _inspector():
    return sa.inspect(op.get_bind())      # a fresh inspector per call: it must see what earlier steps just created


def add_column(table_name: str, column: sa.Column) -> None:
    if column.name in {c["name"] for c in _inspector().get_columns(table_name)}:
        return
    op.add_column(table_name, column)


def create_table(table_name: str, *columns, **kw) -> None:
    if _inspector().has_table(table_name):
        return
    op.create_table(table_name, *columns, **kw)


def create_index(index_name: str, table_name: str, columns, **kw) -> None:
    if index_name in {i["name"] for i in _inspector().get_indexes(table_name)}:
        return
    op.create_index(index_name, table_name, columns, **kw)


def create_check_constraint(constraint_name: str, table_name: str, condition, **kw) -> None:
    # the metadata naming convention prefixes check constraints ("ck_<table>_<name>"), so match on the suffix too
    existing = [c["name"] or "" for c in _inspector().get_check_constraints(table_name)]
    if any(n == constraint_name or n.endswith(f"_{constraint_name}") for n in existing):
        return
    op.create_check_constraint(constraint_name, table_name, condition, **kw)
