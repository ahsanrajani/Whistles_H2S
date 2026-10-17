"""P1.5a — the seeded RBAC catalogue and the permission read layer.

Enforcement (the ``@requires`` decorator, the route×role matrix, deleting the
``admin_only`` list) is P1.5b; here we only check the catalogue is right and
``db/repositories/rbac.py`` answers correctly.
"""
from db import repositories as repo

from ._db import ApiTestCase, DbTestCase

AREAS = {"care", "listening", "reporting", "templates", "queue", "admin"}
VERBS = {"view", "create", "edit", "delete", "export", "approve"}


class CatalogueTests(DbTestCase):
    def _s(self):
        return self.db.session

    def test_six_roles_and_thirty_six_permissions(self):
        cat = repo.rbac.catalogue(self._s())
        keys = {row[0] for row in cat["roles"]}
        self.assertEqual(keys, {"agent", "senior_agent", "supervisor",
                                "team_lead", "admin", "bank_viewer"})
        perms = repo.rbac.permissions_for_roles(
            self._s(), ["agent", "senior_agent", "supervisor",
                        "team_lead", "admin", "bank_viewer"])
        # union across all roles never invents an area/verb outside the grid
        self.assertTrue({a for a, _ in perms} <= AREAS)
        self.assertTrue({v for _, v in perms} <= VERBS)

    def test_admin_holds_every_permission(self):
        perms = repo.rbac.permissions_for_roles(self._s(), ["admin"])
        self.assertEqual(perms, {(a, v) for a in AREAS for v in VERBS})

    def test_agent_is_scoped_and_has_no_admin(self):
        # 0033_care_console_scoping narrowed agent to Care only (Hamza:
        # "the agent accounts should be able to access only the
        # conversations assigned to them, nothing else") -- listening/
        # reporting/queue are gone, care:view/create/edit + templates:view
        # (in-composer knowledge-base search) remain.
        s = self._s()
        self.assertTrue(repo.rbac.has_permission(s, ["agent"], "care", "view"))
        self.assertTrue(repo.rbac.has_permission(s, ["agent"], "templates", "view"))
        self.assertFalse(repo.rbac.has_permission(s, ["agent"], "listening", "view"))
        self.assertFalse(repo.rbac.has_permission(s, ["agent"], "reporting", "view"))
        self.assertFalse(repo.rbac.has_permission(s, ["agent"], "queue", "view"))
        self.assertFalse(repo.rbac.has_permission(s, ["agent"], "listening", "edit"))
        self.assertFalse(repo.rbac.has_permission(s, ["agent"], "admin", "view"))

    def test_supervisor_is_scoped_to_the_care_console(self):
        # 0033_care_console_scoping (Hamza: "supervisor accounts should be
        # able to access only the care console") -- care/queue/templates
        # stay, listening and reporting are gone.
        s = self._s()
        self.assertTrue(repo.rbac.has_permission(s, ["supervisor"], "care", "approve"))
        self.assertTrue(repo.rbac.has_permission(s, ["supervisor"], "queue", "edit"))
        self.assertTrue(repo.rbac.has_permission(s, ["supervisor"], "templates", "approve"))
        self.assertFalse(repo.rbac.has_permission(s, ["supervisor"], "listening", "view"))
        self.assertFalse(repo.rbac.has_permission(s, ["supervisor"], "reporting", "view"))
        self.assertFalse(repo.rbac.has_permission(s, ["supervisor"], "reporting", "approve"))

    def test_bank_viewer_is_read_listening_plus_report_export(self):
        perms = repo.rbac.permissions_for_roles(self._s(), ["bank_viewer"])
        self.assertEqual(
            perms, {("listening", "view"), ("reporting", "view"), ("reporting", "export")})

    def test_multiple_roles_union_their_grants(self):
        s = self._s()
        self.assertTrue(
            repo.rbac.has_permission(s, ["agent", "bank_viewer"], "reporting", "export"))
        self.assertFalse(
            repo.rbac.has_permission(s, ["agent", "bank_viewer"], "admin", "edit"))

    def test_unknown_role_grants_nothing(self):
        self.assertEqual(repo.rbac.permissions_for_roles(self._s(), ["nope"]), set())
        self.assertFalse(repo.rbac.has_permission(self._s(), [], "listening", "view"))


class SeededUsersTests(ApiTestCase):
    def test_seeded_users_carry_their_primary_role_in_user_role(self):
        connection = self.app.db_operator()
        try:
            row = connection.execute(
                'SELECT id, role FROM "user" WHERE username=?', ("admin",)).fetchone()
            self.assertEqual(row[1], "admin")
            self.assertEqual(repo.rbac.roles_for_user(connection.session, row[0]),
                             ["admin"])
            bank = connection.execute(
                'SELECT id FROM "user" WHERE username=?', ("bank",)).fetchone()[0]
            self.assertEqual(repo.rbac.roles_for_user(connection.session, bank),
                             ["bank_viewer"])
        finally:
            connection.close()
