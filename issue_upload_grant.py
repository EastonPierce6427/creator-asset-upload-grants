#!/usr/bin/env python3
"""Mint one presigned upload grant from the command line.

    export INFRAI_API_KEY=...
    python issue_upload_grant.py --creator ana --release r-104 \
        --class master --file album-masters.zip --content-type application/zip --bytes 734003200
"""
from __future__ import annotations

import argparse
import json
import sys

from asset_vault.infrai_client import InfraiClient, InfraiError
from asset_vault.upload_policy import PolicyRejected, UploadRequest
from asset_vault.vault import AssetVault


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a presigned browser upload URL")
    parser.add_argument("--creator", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--class", dest="asset_class", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--content-type", required=True)
    parser.add_argument("--bytes", type=int, required=True)
    args = parser.parse_args()

    request = UploadRequest(
        creator_id=args.creator,
        asset_class=args.asset_class,
        filename=args.file,
        content_type=args.content_type,
        declared_bytes=args.bytes,
        release_id=args.release,
    )

    vault = AssetVault(InfraiClient())
    try:
        grant = vault.grant_upload(request)
    except PolicyRejected as rejected:
        print(json.dumps({"accepted": False, "reason": rejected.reason}, indent=2))
        return 2
    except InfraiError as error:
        print(json.dumps({"accepted": False, "code": error.code, "detail": error.message}, indent=2))
        return 2

    print(json.dumps(
        {
            "accepted": True,
            "key": grant.key,
            "uploadUrl": grant.upload_url,
            "method": "PUT",
            "contentType": grant.content_type,
            "expiresSeconds": grant.expires_seconds,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
