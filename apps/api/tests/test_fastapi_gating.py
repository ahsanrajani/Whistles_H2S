"""P1.10 — every FastAPI ``/api/v1`` route is gated.

The Flask ``protect_portal`` deny-by-default is gone for the ported routes;
its replacement is ``deps.guard`` on every route bar the pre-auth handful.
This walks the live route table and fails if any route is neither exempt nor
carries a ``guard`` dependency.
"""
import unittest

from fastapi.routing import APIRoute

from asgi import fastapi_app


def _all_api_routes():
    """Flatten APIRoutes out of fastapi_app, descending through the lazy
    `_IncludedRouter` placeholders this FastAPI version keeps in `.routes`
    (their real routes hang off `.original_router`)."""
    out, stack = [], list(fastapi_app.routes)
    while stack:
        route = stack.pop()
        if isinstance(route, APIRoute):
            if route.path.startswith("/api/v1"):
                out.append(route)
        elif hasattr(route, "original_router"):
            stack.extend(route.original_router.routes)
        elif hasattr(route, "routes"):
            stack.extend(route.routes)
    return out

# csrf bootstrap, the login/logout pair, the current-user probe, and the OAuth
# bounce — all necessarily reachable before there is a session.
_EXEMPT = {
    "/api/v1/csrf",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/oauth/google/start",
    "/api/v1/auth/oauth/google/callback",
}


def _is_guarded(route: APIRoute) -> bool:
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if getattr(dep.call, "_guru_guard", None) is not None:
            return True
        stack.extend(dep.dependencies)
    return False


class FastApiGatingTests(unittest.TestCase):
    def _api_routes(self):
        return _all_api_routes()

    def test_there_are_routes_to_check(self):
        self.assertGreater(len(self._api_routes()), 30)

    def test_every_api_route_is_exempt_or_guarded(self):
        ungated = sorted(
            f"{sorted(r.methods)} {r.path}"
            for r in self._api_routes()
            if r.path not in _EXEMPT and not _is_guarded(r))
        self.assertEqual(ungated, [], f"ungated FastAPI routes: {ungated}")

    def test_exempt_paths_all_exist(self):
        live = {r.path for r in self._api_routes()}
        self.assertTrue(_EXEMPT.issubset(live), _EXEMPT - live)


if __name__ == "__main__":
    unittest.main()
