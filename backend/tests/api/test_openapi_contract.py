"""The committed OpenAPI contract must not drift (SC-008, T050)."""

from app.cli import OPENAPI_PATH, render_openapi


def test_committed_openapi_matches_the_app() -> None:
    assert OPENAPI_PATH.is_file(), "run `python -m app.cli export-openapi`"
    assert OPENAPI_PATH.read_text(encoding="utf-8") == render_openapi()


def test_openapi_lists_the_user_story_routes() -> None:
    schema = render_openapi()
    for path in (
        '"/auth/login"',
        '"/samples/{sample_id}/advance"',
        '"/samples/{sample_id}/qc"',
        '"/batches/{batch_id}/advance"',
        '"/metrics/tat"',
        '"/samples/{sample_id}/report"',
        '"/portal-pushes/{push_id}/retry"',
    ):
        assert path in schema
