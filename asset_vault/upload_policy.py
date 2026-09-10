"""Typed request models and the upload rules for each class of creator asset.

A creator sells digital goods, so an upload is never just "a file". A paid
master is private and large; a storefront preview is public-facing and small;
an attachment on a subscriber update sits in between. The class decides the
key prefix, the accepted content type, the byte ceiling and how long the
signed URL lives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple

ASSET_CLASSES = ("master", "preview", "update_attachment")

_RULES: Dict[str, Tuple[Tuple[str, ...], int, int]] = {
    # class -> (accepted content types, max bytes, url lifetime in seconds)
    "master": (("application/zip", "audio/wav", "video/mp4", "application/pdf"), 4 * 1024 ** 3, 900),
    "preview": (("image/png", "image/jpeg", "image/webp"), 8 * 1024 ** 2, 300),
    "update_attachment": (("image/png", "image/jpeg", "application/pdf"), 64 * 1024 ** 2, 600),
}

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")


class PolicyRejected(Exception):
    """The requested upload is outside what this asset class allows."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class UploadRequest:
    creator_id: str
    asset_class: str
    filename: str
    content_type: str
    declared_bytes: int
    release_id: str


@dataclass(frozen=True)
class UploadGrantPlan:
    """What the presign call should ask for, decided before any network work."""

    key: str
    content_type: str
    max_bytes: int
    expires_seconds: int
    idempotency_key: str


def plan_upload(request: UploadRequest) -> UploadGrantPlan:
    """Turn a creator's upload request into the exact grant we are willing to sign."""
    if request.asset_class not in _RULES:
        raise PolicyRejected(f"unknown asset class {request.asset_class!r}")
    if not _SAFE_FILENAME.match(request.filename):
        raise PolicyRejected(f"filename {request.filename!r} is not an accepted object name")

    accepted, ceiling, lifetime = _RULES[request.asset_class]
    if request.content_type not in accepted:
        raise PolicyRejected(
            f"{request.content_type} is not accepted for asset class {request.asset_class}"
        )
    if request.declared_bytes <= 0 or request.declared_bytes > ceiling:
        raise PolicyRejected(
            f"{request.declared_bytes} bytes is outside the {ceiling} byte ceiling for "
            f"{request.asset_class}"
        )

    key = f"creators/{request.creator_id}/{request.asset_class}/{request.release_id}/{request.filename}"
    return UploadGrantPlan(
        key=key,
        content_type=request.content_type,
        max_bytes=ceiling,
        expires_seconds=lifetime,
        # Same release + same filename replays the same grant, so a retried
        # request never mints a second slot for one asset.
        idempotency_key=f"grant:{request.creator_id}:{request.release_id}:{request.filename}",
    )
