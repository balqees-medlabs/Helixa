"""US4 report upload, storage and retrieval (T043, FR-016/SC-007).

The QC gate, allowlist and size cap are enforced before anything reaches disk;
stored metadata includes the SHA-256 and only report-reader roles may retrieve
either the metadata or the bytes.
"""

import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("database_url", "reports_root")

PDF = b"%PDF-1.4\n% test report\n"


def _case_id() -> str:
    return f"REP-{uuid.uuid4().hex[:12]}"


def _create_sample(client: TestClient) -> str:
    response = client.post("/samples", json={"case_id": _case_id()})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _pass_qc(client: TestClient, sample_id: str) -> None:
    response = client.post(f"/samples/{sample_id}/qc", json={"kind": "qc", "passed": True})
    assert response.status_code == 200, response.text


def _upload(
    client: TestClient, sample_id: str, content: bytes = PDF, content_type: str = "application/pdf"
):
    return client.post(
        f"/samples/{sample_id}/report",
        files={"file": ("report.pdf", content, content_type)},
    )


def test_upload_requires_a_passing_qc_result(
    genomics_client: TestClient, bioinformatics_client: TestClient, reports_root
) -> None:
    sample_id = _create_sample(genomics_client)
    blocked = _upload(bioinformatics_client, sample_id)
    assert blocked.status_code == 409
    assert "quality control" in blocked.json()["detail"].lower()
    assert not reports_root.exists()


def test_upload_rejects_wrong_type_and_oversize(
    genomics_client: TestClient, bioinformatics_client: TestClient, reports_root
) -> None:
    sample_id = _create_sample(genomics_client)
    _pass_qc(bioinformatics_client, sample_id)

    wrong_type = _upload(bioinformatics_client, sample_id, content_type="text/plain")
    assert wrong_type.status_code == 415

    oversize = _upload(bioinformatics_client, sample_id, content=PDF + b"x" * 2048)
    assert oversize.status_code == 413
    assert not reports_root.exists()


def test_upload_stores_sha256_and_serves_authorized_readers(
    genomics_client: TestClient,
    bioinformatics_client: TestClient,
    admin_client: TestClient,
    trf_client: TestClient,
    molecular_client: TestClient,
    reports_root,
) -> None:
    sample_id = _create_sample(genomics_client)
    _pass_qc(bioinformatics_client, sample_id)

    response = _upload(bioinformatics_client, sample_id)
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert report["size_bytes"] == len(PDF)
    assert report["content_type"] == "application/pdf"
    assert report["push_status"] == "queued"
    assert report["push_id"]

    stored_path = Path(report["path"])
    assert stored_path.is_file()
    assert stored_path.read_bytes() == PDF

    for reader in (admin_client, bioinformatics_client, genomics_client):
        metadata = reader.get(f"/reports/{report['id']}")
        assert metadata.status_code == 200
        assert metadata.json()["sha256"] == report["sha256"]
        download = reader.get(f"/reports/{report['id']}/file")
        assert download.status_code == 200
        assert download.content == PDF
        assert download.headers["content-type"] == "application/pdf"

    for denied in (trf_client, molecular_client):
        assert denied.get(f"/reports/{report['id']}").status_code == 403
        assert denied.get(f"/reports/{report['id']}/file").status_code == 403


def test_upload_is_bioinformatics_only(genomics_client: TestClient, reports_root) -> None:
    sample_id = _create_sample(genomics_client)
    assert _upload(genomics_client, sample_id).status_code == 403


def test_unknown_report_is_not_found(admin_client: TestClient, reports_root) -> None:
    assert admin_client.get(f"/reports/{uuid.uuid4()}").status_code == 404
    assert admin_client.get(f"/reports/{uuid.uuid4()}/file").status_code == 404
