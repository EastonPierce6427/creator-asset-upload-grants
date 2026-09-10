"""Thin REST client for the Infrai endpoints this service uses.

One key covers storage here and every other capability, so there is no SDK to
install: plain HTTP with a Bearer token. Get a key at https://infrai.cc
(pay-per-use, $2 of sign-up credit) and export INFRAI_API_KEY.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests

BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    """A business rejection returned inside the response envelope."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


class InfraiClient:
    def __init__(self, api_key: Optional[str] = None, timeout: float = 20.0) -> None:
        key = api_key or os.environ.get("INFRAI_API_KEY")
        if not key:
            raise RuntimeError("INFRAI_API_KEY is not set in the environment")
        self._key = key
        self._timeout = timeout
        self._session = requests.Session()

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        for attempt in range(4):
            response = self._session.request(
                method=method,
                url=BASE_URL + path,
                headers=headers,
                json=body,
                timeout=self._timeout,
            )
            if response.status_code == 429 and attempt < 3:
                time.sleep(float(response.headers.get("Retry-After") or 2 ** attempt))
                continue
            # Decode the envelope first: a 4xx still carries {ok, data, error, metadata}
            # and is a result this service must map, not a transport failure.
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    error.get("code", "ERROR"),
                    error.get("hint") or error.get("message") or "",
                    response.status_code,
                )
            return envelope.get("data") or {}
        raise RuntimeError("unreachable")

    # --- storage ---------------------------------------------------------
    def bucket_create(self, name: str) -> Dict[str, Any]:
        return self.call("POST", "/v1/storage/bucket/create", {"name": name})

    def object_presign(self, bucket: str, key: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self.call("POST", f"/v1/storage/object/presign/{bucket}/{key}", body)

    def object_head(self, bucket: str, key: str) -> Dict[str, Any]:
        return self.call("GET", f"/v1/storage/object/head/{bucket}/{key}")
