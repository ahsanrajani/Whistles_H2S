"""The idempotent migration helpers: an object that already exists is skipped (a fresh database, where the baseline
was built from the current models), one that is missing is created (an older database)."""
import unittest

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from db import migration_guards as guards

from . import owner_engine      # DDL is an owner privilege; every statement here is rolled back


class MigrationGuardTests(unittest.TestCase):
    def setUp(self):
        self.conn = owner_engine.connect()
        self.addCleanup(self.conn.close)
        self.tx = self.conn.begin()
        self.addCleanup(lambda: self.tx.is_active and self.tx.rollback())
        self.conn.execute(sa.text("CREATE TABLE guard_demo (id integer PRIMARY KEY, name text)"))

    def _columns(self):
        return [c["name"] for c in sa.inspect(self.conn).get_columns("guard_demo")]

    def test_add_column_is_skipped_when_present_and_created_when_missing(self):
        with Operations.context(MigrationContext.configure(self.conn)):
            guards.add_column("guard_demo", sa.Column("name", sa.Text()))          # exists: no error, no duplicate
            guards.add_column("guard_demo", sa.Column("extra", sa.Integer()))      # missing: created
            guards.add_column("guard_demo", sa.Column("extra", sa.Integer()))      # now exists: skipped
        self.assertEqual(sorted(self._columns()), ["extra", "id", "name"])

    def test_create_table_and_index_are_idempotent(self):
        with Operations.context(MigrationContext.configure(self.conn)):
            guards.create_table("guard_demo", sa.Column("id", sa.Integer(), primary_key=True))   # exists: skipped
            guards.create_table("guard_demo_two", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("k", sa.Text()))
            guards.create_table("guard_demo_two", sa.Column("id", sa.Integer(), primary_key=True))  # skipped
            guards.create_index("ix_guard_demo_name", "guard_demo", ["name"])
            guards.create_index("ix_guard_demo_name", "guard_demo", ["name"])                    # skipped
        names = [i["name"] for i in sa.inspect(self.conn).get_indexes("guard_demo")]
        self.assertEqual(names.count("ix_guard_demo_name"), 1)
        self.assertTrue(sa.inspect(self.conn).has_table("guard_demo_two"))

    def test_check_constraint_matches_the_prefixed_convention_name(self):
        # the project's naming convention stores "ck_<table>_<name>"; the helper must not try to add it twice
        with Operations.context(MigrationContext.configure(self.conn)):
            self.conn.execute(sa.text("ALTER TABLE guard_demo ADD CONSTRAINT ck_guard_demo_ck_name_len CHECK (length(name) < 40)"))
            guards.create_check_constraint("ck_name_len", "guard_demo", "length(name) < 40")   # present under its full name: skipped
            guards.create_check_constraint("ck_name_other", "guard_demo", "length(name) < 80")  # missing: created
        found = [c["name"] for c in sa.inspect(self.conn).get_check_constraints("guard_demo")]
        self.assertEqual(len(found), 2)


class RolePasswordTests(unittest.TestCase):
    """0003_rls gives guru_app / guru_operator the owner's password (that is what db/session.py puts in the derived
    role URLs), unless GURU_ROLE_PASSWORD overrides it; with neither it stays 'guru'."""

    def _load(self):
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic", "versions", "0003_rls.py")
        spec = importlib.util.spec_from_file_location("rev_0003", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_precedence_override_then_owner_then_default(self):
        import os
        from unittest import mock
        mod = self._load()
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://own:ownerpw@h/db"}, clear=False):
            os.environ.pop("GURU_ROLE_PASSWORD", None)
            self.assertEqual(mod._role_password(), "ownerpw")
            os.environ["GURU_ROLE_PASSWORD"] = "override"
            self.assertEqual(mod._role_password(), "override")
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://own@h/db"}, clear=False):
            os.environ.pop("GURU_ROLE_PASSWORD", None)
            self.assertEqual(mod._role_password(), "guru")
