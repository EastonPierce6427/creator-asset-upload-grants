"""The service layer: mint browser upload grants, then hand out delivery links."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .infrai_client import InfraiClient, InfraiError
from .upload_policy import UploadGrantPlan, UploadRequest, plan_upload

BUCKET = "creator-assets"


@dataclass(frozen=True)
class UploadGrant:
    upload_url: str
    key: str
    content_type: str
    expires_seconds: int


@dataclass(frozen=True)
class DeliveryLink:
    key: str
    url: Optional[str]
    available: bool


class AssetVault:
    def __init__(self, client: InfraiClient, bucket: str = BUCKET) -> None:
        self._client = client
        self._bucket = bucket
        self._bucket_ready = False

    def ensure_bucket(self) -> None:
        """Create the storage bucket the first time the service needs it."""
        if self._bucket_ready:
            return
        try:
            self._client.bucket_create(self._bucket)
        except InfraiError:
            # The bucket is already standing from an earlier boot.
            pass
        self._bucket_ready = True

    def grant_upload(self, request: UploadRequest) -> UploadGrant:
        """Decide the policy, then sign a PUT URL the browser uploads to directly."""
        plan: UploadGrantPlan = plan_upload(request)
        self.ensure_bucket()
        data = self._client.object_presign(
            self._bucket,
            plan.key,
            {
                "op": "put",
                "expires_seconds": plan.expires_seconds,
                "content_type": plan.content_type,
                "max_bytes": plan.max_bytes,
                "idempotency_key": plan.idempotency_key,
            },
        )
        return UploadGrant(
            upload_url=data["url"],
            key=plan.key,
            content_type=plan.content_type,
            expires_seconds=plan.expires_seconds,
        )

    def delivery_link(self, key: str, filename: str, expires_seconds: int = 300) -> DeliveryLink:
        """Sign a short-lived download for a buyer, once the asset is in place."""
        self.ensure_bucket()
        head = self._client.object_head(self._bucket, key)
        if not head.get("found"):
            return DeliveryLink(key=key, url=None, available=False)
        data = self._client.object_presign(
            self._bucket,
            key,
            {
                "op": "get",
                "expires_seconds": expires_seconds,
                "response_disposition": f'attachment; filename="{filename}"',
            },
        )
        return DeliveryLink(key=key, url=data["url"], available=True)
