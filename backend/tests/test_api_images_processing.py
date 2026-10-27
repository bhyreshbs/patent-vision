import io

import cv2
import numpy as np
import pytest
from PIL import Image as PILImage
from sqlalchemy import select

from app.core import database
from app.core.storage import storage
from app.models import AIResult, Image, ProcessingJob
from app.services.processing import recover_interrupted
from tests import synthetic
from tests.conftest import upload


def png_bytes(arr_bgr) -> bytes:
    return synthetic.encode(arr_bgr)


def decode(data: bytes, flags=cv2.IMREAD_UNCHANGED):
    return cv2.imdecode(np.frombuffer(data, np.uint8), flags)


# ---------------- upload ----------------
def test_upload_stores_original_and_metadata(client, auth, project, organizer_photo):
    img, _, data = organizer_photo
    r = upload(client, auth, project["id"], data, "My Organizer (1).png", view="Top")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["original_filename"] == "My_Organizer_1_.png"
    assert body["view_type"] == "Top" and body["processing_status"] == "Uploaded"
    assert (body["width"], body["height"]) == (img.shape[1], img.shape[0])
    assert body["mime_type"] == "image/png" and body["size_bytes"] == len(data)
    assert body["project_id"] == project["id"] and body["result"] is None

    with database.SessionLocal() as db:
        row = db.get(Image, body["id"])
        assert storage.read_bytes(row.storage_key) == data  # original preserved byte-for-byte
        assert not row.storage_key.startswith("/") and ":" not in row.storage_key  # relative key

    original = client.get(body["original_url"], headers=auth)
    assert original.status_code == 200 and original.content == data


def test_upload_defaults_to_other_view_not_front(client, auth, project, organizer_photo):
    r = client.post(
        f"/projects/{project['id']}/images",
        files={"file": ("a.png", organizer_photo[2], "image/png")},
        headers=auth,
    )
    assert r.status_code == 201 and r.json()["view_type"] == "Other"


def test_upload_rejections_have_clear_structured_errors(client, auth, project):
    pid = project["id"]
    r = upload(client, auth, pid, b"", "empty.png")
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_file"
    r = upload(client, auth, pid, b"not an image at all", "bad.png")
    assert r.status_code == 422 and r.json()["error"]["next_action"]
    buf = io.BytesIO()
    PILImage.new("RGB", (100, 100)).save(buf, "GIF")
    r = upload(client, auth, pid, buf.getvalue(), "a.gif", "image/gif")
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_image_type"
    r = upload(client, auth, pid, png_bytes(np.zeros((100, 100, 3), np.uint8)), view="Sideways")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_view"
    assert client.get(f"/projects/{pid}/images", headers=auth).json() == []  # nothing half-saved


def test_upload_size_limit(client, auth, project, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2000)
    big = png_bytes(np.random.default_rng(0).integers(0, 255, (200, 200, 3), dtype=np.uint8))
    r = upload(client, auth, project["id"], big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_cannot_upload_to_someone_elses_project(client, other_auth, project, organizer_photo):
    r = upload(client, other_auth, project["id"], organizer_photo[2])
    assert r.status_code == 404


def test_view_can_be_corrected_and_persists(client, auth, project, organizer_photo):
    iid = upload(client, auth, project["id"], organizer_photo[2], view="Front").json()["id"]
    r = client.patch(f"/images/{iid}", json={"view_type": "Left"}, headers=auth)
    assert r.status_code == 200 and r.json()["view_type"] == "Left"
    assert client.get(f"/images/{iid}", headers=auth).json()["view_type"] == "Left"
    assert client.patch(f"/images/{iid}", json={"view_type": "Nope"}, headers=auth).status_code == 422


def test_image_listing_and_privacy(client, auth, other_auth, project, organizer_photo):
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    assert [i["id"] for i in client.get(f"/projects/{project['id']}/images", headers=auth).json()] == [iid]
    assert client.get(f"/images/{iid}", headers=other_auth).status_code == 404
    assert client.get(f"/images/{iid}/original", headers=other_auth).status_code == 404
    assert client.get("/images/9999", headers=auth).status_code == 404


# ---------------- end-to-end processing ----------------
def test_upload_process_verify_and_download(client, auth, project, organizer_photo):
    img, truth, data = organizer_photo
    iid = upload(client, auth, project["id"], data).json()["id"]

    r = client.post(f"/ai/process/{iid}", headers=auth)
    assert r.status_code == 202
    assert r.json()["job"]["retry_count"] == 0

    image = client.get(f"/images/{iid}", headers=auth).json()
    assert image["processing_status"] == "Completed", image
    res = image["result"]
    assert res["status"] == "Completed" and res["error_message"] is None
    assert image["job"]["job_status"] == "Completed" and image["job"]["completed_at"]
    assert res["metrics"]["mask_candidate"] in {"grabcut", "foreground-mask"}

    got = {}
    for kind in ("drawing", "background_removed", "mask", "outline", "original"):
        url = res["urls"][kind]
        assert url, kind
        d = client.get(url, headers=auth)
        assert d.status_code == 200, kind
        assert d.headers["content-type"].startswith("image/")
        got[kind] = d.content

    mask = decode(got["mask"], cv2.IMREAD_GRAYSCALE)
    assert mask.shape == truth.shape and set(np.unique(mask)) <= {0, 255}
    inter = np.count_nonzero((mask > 0) & (truth > 0))
    assert inter / np.count_nonzero((mask > 0) | (truth > 0)) > 0.95
    outline = decode(got["outline"], cv2.IMREAD_COLOR)
    assert outline.shape == img.shape
    drawing = decode(got["drawing"], cv2.IMREAD_GRAYSCALE)
    assert drawing[:5, :5].min() == 255 and (drawing < 128).any()
    cut = decode(got["background_removed"])
    assert cut.shape[2] == 4

    # result endpoints
    rid = res["id"]
    assert client.get(f"/ai/results/{rid}", headers=auth).json()["status"] == "Completed"
    dl = client.get(f"/ai/results/{rid}/download?kind=drawing&download=true", headers=auth)
    assert "attachment" in dl.headers["content-disposition"] and "photo_drawing.png" in dl.headers["content-disposition"]

    # files live under the storage root as relative keys
    with database.SessionLocal() as db:
        row = db.scalar(select(AIResult).where(AIResult.id == rid))
        for key in (row.mask_path, row.outline_path, row.patent_drawing_path, row.background_removed_path):
            assert not key.startswith("/") and ":" not in key
            assert storage.exists(key)

    # no local filesystem paths ever leak through the API
    leaked = str(storage.root)
    for resp in (client.get(f"/images/{iid}", headers=auth), client.get(f"/ai/results/{rid}", headers=auth)):
        assert leaked not in resp.text and "storage_key" not in resp.text and "_path" not in resp.text


def test_downloads_are_owner_only(client, auth, other_auth, project, organizer_photo):
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    client.post(f"/ai/process/{iid}", headers=auth)
    rid = client.get(f"/images/{iid}", headers=auth).json()["result"]["id"]
    for kind in ("drawing", "mask", "original"):
        assert client.get(f"/ai/results/{rid}/download?kind={kind}", headers=other_auth).status_code == 404
        assert client.get(f"/ai/results/{rid}/download?kind={kind}").status_code == 401
    assert client.get(f"/ai/results/{rid}", headers=other_auth).status_code == 404
    assert client.get(f"/ai/results/{rid}/download?kind=../../etc/passwd", headers=auth).status_code == 422
    assert client.post(f"/ai/process/{iid}", headers=other_auth).status_code == 404


def test_failed_processing_is_never_reported_as_completed(client, auth, project):
    blank = png_bytes(np.full((300, 400, 3), 235, np.uint8))
    iid = upload(client, auth, project["id"], blank).json()["id"]
    assert client.post(f"/ai/process/{iid}", headers=auth).status_code == 202

    image = client.get(f"/images/{iid}", headers=auth).json()
    assert image["processing_status"] == "Failed"
    res = image["result"]
    assert res["status"] == "Failed" and res["failed_stage"] and res["error_message"]
    assert image["job"]["job_status"] == "Failed" and image["job"]["failed_stage"] == res["failed_stage"]
    assert res["urls"]["drawing"] is None and res["urls"]["mask"] is None
    r = client.get(f"/ai/results/{res['id']}/download?kind=drawing", headers=auth)
    assert r.status_code == 409 and r.json()["error"]["code"] == "result_not_ready"
    assert not any(storage.root.joinpath("generated").rglob("*.png"))  # no partial outputs left


def test_retry_after_failure_succeeds_and_counts_retries(client, auth, project, organizer_photo):
    pid = project["id"]
    iid = upload(client, auth, pid, organizer_photo[2]).json()["id"]
    # simulate an earlier failure
    with database.SessionLocal() as db:
        image = db.get(Image, iid)
        image.processing_status = "Failed"
        db.add(ProcessingJob(image_id=iid, job_status="Failed", error_message="boom", failed_stage="segmentation"))
        db.add(AIResult(image_id=iid, status="Failed", error_message="boom", failed_stage="segmentation"))
        db.commit()

    r = client.post(f"/ai/process/{iid}", headers=auth)
    assert r.status_code == 202 and r.json()["job"]["retry_count"] == 1
    image = client.get(f"/images/{iid}", headers=auth).json()
    assert image["processing_status"] == "Completed"
    assert image["result"]["error_message"] is None and image["result"]["failed_stage"] is None
    assert image["job"]["error_message"] is None and image["job"]["retry_count"] == 1

    with database.SessionLocal() as db:  # retries never create duplicate rows
        assert len(db.scalars(select(AIResult).where(AIResult.image_id == iid)).all()) == 1
        assert len(db.scalars(select(ProcessingJob).where(ProcessingJob.image_id == iid)).all()) == 1


def test_reprocessing_a_completed_image_is_idempotent(client, auth, project, organizer_photo):
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    client.post(f"/ai/process/{iid}", headers=auth)
    first = client.get(f"/images/{iid}", headers=auth).json()["result"]
    client.post(f"/ai/process/{iid}", headers=auth)
    second = client.get(f"/images/{iid}", headers=auth).json()
    assert second["processing_status"] == "Completed" and second["result"]["id"] == first["id"]


@pytest.mark.parametrize("active", ["Queued", "Processing"])
def test_cannot_double_queue_an_active_job(client, auth, project, organizer_photo, active):
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    with database.SessionLocal() as db:
        db.get(Image, iid).processing_status = active
        db.commit()
    r = client.post(f"/ai/process/{iid}", headers=auth)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_processing"
    assert client.delete(f"/images/{iid}", headers=auth).status_code == 409


def test_missing_original_file_fails_with_visible_error(client, auth, project, organizer_photo):
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    with database.SessionLocal() as db:
        storage.delete(db.get(Image, iid).storage_key)
    client.post(f"/ai/process/{iid}", headers=auth)
    image = client.get(f"/images/{iid}", headers=auth).json()
    assert image["processing_status"] == "Failed" and image["result"]["failed_stage"] == "load"
    assert "missing" in image["result"]["error_message"]
    assert client.get(image["original_url"], headers=auth).status_code == 404


def test_unexpected_crash_is_recorded_as_failure(client, auth, project, organizer_photo, monkeypatch):
    from app.services import processing

    def boom(*a, **k):
        raise RuntimeError("secret internal detail /home/user/x.py")

    monkeypatch.setattr(processing, "run_pipeline", boom)
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    client.post(f"/ai/process/{iid}", headers=auth)
    image = client.get(f"/images/{iid}", headers=auth).json()
    assert image["processing_status"] == "Failed"
    assert "secret internal detail" not in image["result"]["error_message"]
    assert "Retry" in image["result"]["error_message"]


def test_missing_sam_checkpoint_surfaces_as_segmentation_failure(client, auth, project, organizer_photo, monkeypatch):
    from app.core.config import get_settings
    from app.services import processing

    monkeypatch.setattr(get_settings(), "segmenter", "sam")
    monkeypatch.setattr(get_settings(), "sam_checkpoint", None)
    processing._segmenter.cache_clear()
    try:
        iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
        client.post(f"/ai/process/{iid}", headers=auth)
        res = client.get(f"/images/{iid}", headers=auth).json()["result"]
        assert res["status"] == "Failed" and res["failed_stage"] == "segmentation"
        assert "checkpoint" in res["error_message"]
    finally:
        processing._segmenter.cache_clear()


def test_process_project_queues_every_image_and_failed_views_can_rerun(client, auth, project, organizer_photo):
    pid = project["id"]
    good = upload(client, auth, pid, organizer_photo[2], view="Front").json()["id"]
    bad = upload(client, auth, pid, png_bytes(np.full((300, 400, 3), 235, np.uint8)), view="Rear").json()["id"]
    r = client.post(f"/ai/process/project/{pid}", headers=auth)
    assert r.status_code == 202 and sorted(r.json()["queued"]) == sorted([good, bad])

    statuses = {i["id"]: i["processing_status"] for i in client.get(f"/projects/{pid}/images", headers=auth).json()}
    assert statuses == {good: "Completed", bad: "Failed"}
    summary = client.get(f"/projects/{pid}", headers=auth).json()
    assert summary["image_count"] == 2 and summary["status_counts"] == {"Completed": 1, "Failed": 1}

    # only the failed view needs reprocessing; each view keeps its own drawing
    assert client.post(f"/ai/process/{bad}", headers=auth).status_code == 202
    assert client.get(f"/images/{good}", headers=auth).json()["result"]["urls"]["drawing"]
    assert client.post("/ai/process/project/9999", headers=auth).status_code == 404


def test_dashboard_summarises_activity(client, auth, project, organizer_photo):
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    client.post(f"/ai/process/{iid}", headers=auth)
    d = client.get("/dashboard", headers=auth).json()
    assert d["project_count"] == 1 and d["image_count"] == 1 and d["status_counts"] == {"Completed": 1}
    assert d["recent_projects"][0]["id"] == project["id"]
    assert d["recent_results"][0]["id"] == iid


def test_interrupted_jobs_are_surfaced_as_failed_on_restart(client, auth, project, organizer_photo):
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    with database.SessionLocal() as db:
        db.get(Image, iid).processing_status = "Processing"
        db.add(ProcessingJob(image_id=iid, job_status="Processing"))
        db.add(AIResult(image_id=iid, status="Processing"))
        db.commit()
    assert recover_interrupted() == 1
    image = client.get(f"/images/{iid}", headers=auth).json()
    assert image["processing_status"] == "Failed" and image["result"]["failed_stage"] == "interrupted"
    assert client.post(f"/ai/process/{iid}", headers=auth).status_code == 202  # and it can be retried


# ---------------- deletion / cleanup ----------------
def test_delete_image_removes_row_and_files(client, auth, project, organizer_photo):
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    client.post(f"/ai/process/{iid}", headers=auth)
    assert any(storage.root.joinpath("generated").rglob("*.png"))
    assert client.delete(f"/images/{iid}", headers=auth).status_code == 204
    assert client.get(f"/images/{iid}", headers=auth).status_code == 404
    assert not any(storage.root.joinpath("generated").rglob("*.png"))
    assert not any(storage.root.joinpath("uploads").rglob("*.*"))
    with database.SessionLocal() as db:
        assert db.scalars(select(AIResult)).all() == [] and db.scalars(select(ProcessingJob)).all() == []


def test_delete_project_cascades_to_db_rows_and_files(client, auth, project, organizer_photo):
    pid = project["id"]
    for _ in range(2):
        iid = upload(client, auth, pid, organizer_photo[2]).json()["id"]
        client.post(f"/ai/process/{iid}", headers=auth)
    assert client.delete(f"/projects/{pid}", headers=auth).status_code == 204
    with database.SessionLocal() as db:
        assert db.scalars(select(Image)).all() == []
        assert db.scalars(select(AIResult)).all() == []
        assert db.scalars(select(ProcessingJob)).all() == []
    assert not any(p.is_file() for p in storage.root.rglob("*"))


def test_foreign_keys_prevent_orphan_results():
    from sqlalchemy.exc import IntegrityError

    with database.SessionLocal() as db:
        db.add(AIResult(image_id=424242, status="Queued"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Image(project_id=999, original_filename="x", storage_key="k", mime_type="image/png",
                     size_bytes=1, width=1, height=1))
        with pytest.raises(IntegrityError):
            db.commit()


def test_storage_rejects_path_traversal():
    with pytest.raises(ValueError):
        storage.path("../outside.txt")
    with pytest.raises(ValueError):
        storage.save_bytes("uploads/../../escape.txt", b"x")
