"""Row-level security for the Phase 2-4 tenant tables (Alembic 0024).

Same proof as ``test_rls.py`` but for the care / analytics / calendar / survey
tables: no ``app.tenant_id`` -> zero rows; a tenant id -> only that tenant's
rows; ``WITH CHECK`` blocks a cross-tenant insert; ``guru_operator`` still sees
everything.
"""
import unittest

import sqlalchemy as sa

from db.session import engine, operator_engine

from . import truncate_all

_TABLES = ("source_state", "outbound_action", "customer", "case", "case_message",
           "care_agent", "metric_fact", "agent_activity", "content_item",
           "survey", "survey_response", "report_schedule")


class Phase234RlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        truncate_all()
        with operator_engine.begin() as c:
            for wid, name in ((1, "Alfa"), (2, "Beta")):
                c.execute(sa.text("INSERT INTO workspace(id,name,market,created_at) "
                                  "VALUES (:i,:n,'PK','now')"), {"i": wid, "n": name})
                cust = c.execute(sa.text(
                    "INSERT INTO customer(workspace_id,display_name) "
                    "VALUES (:i,:n) RETURNING id"), {"i": wid, "n": name}).scalar()
                c.execute(sa.text(
                    'INSERT INTO "case"(workspace_id,customer_id,channel) '
                    "VALUES (:i,:c,'x')"), {"i": wid, "c": cust})
                c.execute(sa.text(
                    "INSERT INTO metric_fact(workspace_id,source,entity_type,metric,day,value) "
                    "VALUES (:i,'meta','page','impressions',CURRENT_DATE,10)"), {"i": wid})
                c.execute(sa.text(
                    "INSERT INTO report_schedule(workspace_id,name,kind,cron) "
                    "VALUES (:i,'r','sla','0 7 * * 1')"), {"i": wid})

    @classmethod
    def tearDownClass(cls):
        truncate_all()

    def test_no_tenant_context_sees_zero_rows(self):
        with engine.connect() as c:
            for t in _TABLES:
                self.assertEqual(
                    c.execute(sa.text(f'SELECT count(*) FROM "{t}"')).scalar(), 0,
                    f"{t} leaked rows with no app.tenant_id")

    def test_tenant_context_scopes_to_its_workspace(self):
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '1', true)"))
            self.assertEqual(
                c.execute(sa.text('SELECT count(*) FROM "case"')).scalar(), 1)
            self.assertEqual(
                c.execute(sa.text("SELECT count(*) FROM metric_fact")).scalar(), 1)
            self.assertEqual(
                c.execute(sa.text("SELECT name FROM report_schedule")).scalar(), "r")
            self.assertEqual(
                c.execute(sa.text("SELECT display_name FROM customer")).scalar(), "Alfa")

    def test_other_tenants_rows_are_invisible(self):
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '2', true)"))
            self.assertEqual(
                c.execute(sa.text("SELECT display_name FROM customer")).scalar(), "Beta")
            self.assertEqual(
                c.execute(sa.text("SELECT count(*) FROM customer "
                                  "WHERE display_name = 'Alfa'")).scalar(), 0)

    def test_with_check_blocks_a_cross_tenant_insert(self):
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '1', true)"))
            with self.assertRaises(Exception):
                c.execute(sa.text(
                    "INSERT INTO report_schedule(workspace_id,name,kind,cron) "
                    "VALUES (2,'x','sla','* * * * *')"))

    def test_operator_engine_bypasses_rls(self):
        with operator_engine.connect() as c:
            self.assertEqual(
                c.execute(sa.text('SELECT count(*) FROM "case"')).scalar(), 2)


if __name__ == "__main__":
    unittest.main()
