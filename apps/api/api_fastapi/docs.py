"""Interactive API documentation backed by the canonical OpenAPI contract."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse


router = APIRouter(include_in_schema=False)

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.yaml"
)


@router.get("/openapi.yaml")
def openapi_contract():
    """Serve the contract of record without generating a second schema."""
    return FileResponse(
        _CONTRACT_PATH,
        media_type="application/yaml",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/docs")
def swagger_ui():
    """Render Swagger UI with same-origin cookies for session-authenticated calls."""
    return get_swagger_ui_html(
        openapi_url="/openapi.yaml",
        title="Guru Ears API - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": True},
    )
