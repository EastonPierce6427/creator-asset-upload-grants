"""The grant decision is where money is at stake, so it is tested without network."""
from __future__ import annotations

import pytest

from asset_vault.upload_policy import PolicyRejected, UploadRequest, plan_upload
from asset_vault.vault import AssetVault


def request(**overrides) -> UploadRequest:
    base = dict(
        creator_id="ana",
        asset_class="preview",
        filename="cover.png",
        content_type="image/png",
        declared_bytes=420_000,
        release_id="r-104",
    )
    base.update(overrides)
    return UploadRequest(**base)


def test_preview_plan_scopes_key_and_lifetime():
    plan = plan_upload(request())
    assert plan.key == "creators/ana/preview/r-104/cover.png"
    assert plan.expires_seconds == 300
    assert plan.max_bytes == 8 * 1024 ** 2


def test_master_gets_a_larger_ceiling_than_a_preview():
    master = plan_upload(request(asset_class="master", filename="masters.zip",
                                 content_type="application/zip", declared_bytes=734_003_200))
    preview = plan_upload(request())
    assert master.max_bytes > preview.max_bytes
    assert master.key.startswith("creators/ana/master/r-104/")


def test_video_is_refused_for_a_storefront_preview():
    with pytest.raises(PolicyRejected):
        plan_upload(request(filename="teaser.mp4", content_type="video/mp4"))


def test_oversized_attachment_is_refused_before_any_call():
    with pytest.raises(PolicyRejected):
        plan_upload(request(asset_class="update_attachment", filename="notes.pdf",
                            content_type="application/pdf", declared_bytes=200 * 1024 ** 2))


def test_traversal_in_a_filename_never_reaches_the_key():
    with pytest.raises(PolicyRejected):
        plan_upload(request(filename="../../other/cover.png"))


def test_retrying_one_upload_replays_the_same_grant():
    assert plan_upload(request()).idempotency_key == plan_upload(request()).idempotency_key


class FakeClient:
    def __init__(self, found: bool) -> None:
        self.found = found
        self.presigned = []

    def bucket_create(self, name):
        return {"name": name}

    def object_head(self, bucket, key):
        return {"found": self.found}

    def object_presign(self, bucket, key, body):
        self.presigned.append((key, body))
        return {"url": f"https://signed.example/{key}"}


def test_delivery_waits_until_the_asset_is_in_place():
    vault = AssetVault(FakeClient(found=False))
    link = vault.delivery_link("creators/ana/master/r-104/masters.zip", "masters.zip")
    assert link.available is False and link.url is None


def test_delivery_signs_a_named_download_once_the_asset_lands():
    client = FakeClient(found=True)
    link = AssetVault(client).delivery_link("creators/ana/master/r-104/masters.zip", "masters.zip")
    assert link.available is True and link.url.startswith("https://signed.example/")
    key, body = client.presigned[-1]
    assert body["op"] == "get"
    assert body["response_disposition"] == 'attachment; filename="masters.zip"'
