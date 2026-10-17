"""Row-level security — drift-proof coverage + isolation across *every*
workspace-scoped table.

``test_rls.py`` / ``test_rls_phase234.py`` name the tables they check. This one
enumerates them from the live schema instead: any ``BASE TABLE`` in ``public``
with a ``workspace_id`` column, plus ``workspace`` itself. A future migration
that adds a tenant table and forgets the policy fails
``test_every_scoped_table_is_policied`` here — the leak path Phase A of the
remaining-work plan is about.

``user`` is the one deliberate exception: it carries ``workspace_id`` (the
user's home workspace) but no policy, because the pre-login lookup by username
runs before any tenant context exists. Every ``user`` read/write in the app
goes through the ``BYPASSRLS`` operator connection; the RLS-enforced
``guru_app`` engine never touches it. The test pins that so a second,
undocumented gap can't hide behind it.
"""
import unittest

import sqlalchemy as sa

from db.session import engine, operator_engine

from . import truncate_all

# workspace_id-bearing tables that intentionally have no policy, each with the
# reason. Anything else without a policy is a bug.
_POLICY_EXEMPT = {
    "user": "pre-login username lookup has no tenant context; all access is via "
            "the BYPASSRLS operator connection",
}


def _scoped_tables(conn) -> list[str]:
    rows = conn.execute(sa.text("""
        SELECT DISTINCT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
         AND t.table_type = 'BASE TABLE'
        WHERE c.table_schema = 'public' AND c.column_name = 'workspace_id'
        UNION
        SELECT 'workspace'
    """)).scalars().all()
    return sorted(rows)


class RlsCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        truncate_all()
        with operator_engine.begin() as c:
            cls.tables = _scoped_tables(c)
            cls.users = {}
            cls.surveys = {}
            cls.cases = {}
            cls.customers = {}
            for wid, name in ((1, "Alfa"), (2, "Beta")):
                c.execute(sa.text(
                    "INSERT INTO workspace(id,name,market,created_at) "
                    "VALUES (:i,:n,'PK','now')"), {"i": wid, "n": name})
                uid = c.execute(sa.text(
                    "INSERT INTO \"user\"(username,password_hash,role,created_at,workspace_id) "
                    "VALUES (:u,'x','bank_viewer','now',:w) RETURNING id"),
                    {"u": f"u{wid}", "w": wid}).scalar()
                cust = c.execute(sa.text(
                    "INSERT INTO customer(workspace_id,display_name) "
                    "VALUES (:i,:n) RETURNING id"), {"i": wid, "n": name}).scalar()
                case = c.execute(sa.text(
                    'INSERT INTO "case"(workspace_id,customer_id,channel) '
                    "VALUES (:i,:c,'x') RETURNING id"), {"i": wid, "c": cust}).scalar()
                sv = c.execute(sa.text(
                    "INSERT INTO survey(workspace_id,name) VALUES (:i,'csat') RETURNING id"),
                    {"i": wid}).scalar()
                cls.users[wid], cls.customers[wid] = uid, cust
                cls.cases[wid], cls.surveys[wid] = case, sv

                # the PII-bearing tables Phase A names, so the isolation check
                # below is a real assertion and not vacuously true
                c.execute(sa.text(
                    "INSERT INTO case_message(case_id,workspace_id,direction,channel,body) "
                    "VALUES (:c,:i,'inbound','x','hello')"), {"c": case, "i": wid})
                c.execute(sa.text(
                    "INSERT INTO item_author(workspace_id,platform,author_hash,first_seen,last_seen) "
                    "VALUES (:i,'meta',:h,'now','now')"), {"i": wid, "h": f"h{wid}"})
                c.execute(sa.text(
                    "INSERT INTO outbound_action(workspace_id,platform,action) "
                    "VALUES (:i,'meta','reply_public')"), {"i": wid})
                c.execute(sa.text(
                    "INSERT INTO metric_fact(workspace_id,source,entity_type,metric,day,value) "
                    "VALUES (:i,'meta','page','impressions',CURRENT_DATE,10)"), {"i": wid})
                c.execute(sa.text(
                    "INSERT INTO content_item(workspace_id,title) VALUES (:i,'draft')"),
                    {"i": wid})
                c.execute(sa.text(
                    "INSERT INTO survey_response(workspace_id,survey_id,token) "
                    "VALUES (:i,:s,:t)"), {"i": wid, "s": sv, "t": f"tok{wid}"})
                c.execute(sa.text(
                    "INSERT INTO agent_activity(workspace_id,user_id,kind) "
                    "VALUES (:i,:u,'login')"), {"i": wid, "u": uid})
                c.execute(sa.text(
                    "INSERT INTO kb_article(workspace_id,title) VALUES (:i,'how-to')"),
                    {"i": wid})

    @classmethod
    def tearDownClass(cls):
        truncate_all()

    # -- enumeration ----------------------------------------------------
    def test_enumeration_finds_the_known_core_tables(self):
        for expected in ("workspace", "brand", "item", "mention", "case",
                         "case_message", "customer", "outbound_action",
                         "metric_fact", "content_item", "survey_response",
                         "agent_activity", "kb_article", "item_author",
                         "project", "report_schedule"):
            self.assertIn(expected, self.tables)

    # -- coverage (the drift guard) -----------------------------------
    def test_every_scoped_table_is_policied(self):
        with operator_engine.connect() as c:
            missing_rls, missing_policy = [], []
            for t in self.tables:
                if t in _POLICY_EXEMPT:
                    continue
                rls_on = c.execute(sa.text(
                    "SELECT relrowsecurity FROM pg_class WHERE relname = :t"),
                    {"t": t}).scalar()
                pol = c.execute(sa.text("""
                    SELECT qual, with_check FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = :t
                      AND policyname = 'tenant_isolation'
                """), {"t": t}).first()
                if not rls_on:
                    missing_rls.append(t)
                if pol is None or pol[0] is None or pol[1] is None:
                    missing_policy.append(t)
        self.assertEqual(missing_rls, [], f"RLS not enabled: {missing_rls}")
        self.assertEqual(missing_policy, [],
                         f"no tenant_isolation USING/WITH CHECK policy: {missing_policy}")

    def test_the_only_unpolicied_scoped_table_is_the_documented_exception(self):
        with operator_engine.connect() as c:
            unpolicied = {
                t for t in self.tables
                if c.execute(sa.text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname='public' "
                    "AND tablename=:t AND policyname='tenant_isolation'"),
                    {"t": t}).scalar() == 0
            }
        self.assertEqual(
            unpolicied, set(_POLICY_EXEMPT),
            f"unexpected scoped tables with no policy: {unpolicied - set(_POLICY_EXEMPT)}; "
            f"if intentional, add them to _POLICY_EXEMPT with a reason")

    # -- isolation, for every enumerated table -----------------------
    def test_a_tenant_1_session_sees_no_tenant_2_rows_anywhere(self):
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '1', true)"))
            leaked = []
            for t in self.tables:
                if t in _POLICY_EXEMPT:
                    continue
                col = "id" if t == "workspace" else "workspace_id"
                other = c.execute(sa.text(
                    f'SELECT count(*) FROM "{t}" WHERE {col} <> 1')).scalar()
                if other:
                    leaked.append((t, other))
            self.assertEqual(leaked, [], f"tenant 1 saw foreign rows: {leaked}")

    def test_the_seeded_pii_tables_are_a_real_check_not_a_vacuous_one(self):
        # each of these has one tenant-1 row and one tenant-2 row; tenant 1 must
        # see exactly its own
        seeded = ("case_message", "item_author", "outbound_action", "metric_fact",
                  "content_item", "survey_response", "agent_activity", "kb_article",
                  "customer", "case")
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '1', true)"))
            for t in seeded:
                self.assertEqual(
                    c.execute(sa.text(f'SELECT count(*) FROM "{t}"')).scalar(), 1,
                    f"{t}: tenant 1 should see exactly its own row")
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '2', true)"))
            for t in seeded:
                self.assertEqual(
                    c.execute(sa.text(f'SELECT count(*) FROM "{t}"')).scalar(), 1,
                    f"{t}: tenant 2 should see exactly its own row")

    def test_with_check_blocks_cross_tenant_insert_on_a_scoped_table(self):
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '1', true)"))
            with self.assertRaises(Exception):
                c.execute(sa.text(
                    "INSERT INTO kb_article(workspace_id,title) VALUES (2,'sneak')"))

    def test_operator_engine_bypasses_rls_everywhere(self):
        with operator_engine.connect() as c:
            for t in ("case_message", "outbound_action", "survey_response",
                      "kb_article", "agent_activity"):
                self.assertEqual(
                    c.execute(sa.text(f'SELECT count(*) FROM "{t}"')).scalar(), 2,
                    f"operator should see both tenants' {t} rows")


if __name__ == "__main__":
    unittest.main()
