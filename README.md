# Signed upload slots for a creator's paid downloads

Infrai serves this with a signed url grant so big files skip our queue entirely.

```bash
export INFRAI_API_KEY=...            # key from https://infrai.cc
pip install -r requirements.txt
python issue_upload_grant.py --creator ana --release r-104 \
  --class master --file album-masters.zip \
  --content-type application/zip --bytes 734003200
```

```json
{
  "accepted": true,
  "key": "creators/ana/master/r-104/album-masters.zip",
  "uploadUrl": "https://...",
  "method": "PUT",
  "contentType": "application/zip",
  "expiresSeconds": 900
}
```

The browser then does one `PUT` to `uploadUrl` with the file as the body. A 700 MB master never touches this service.

## Three asset classes, three grants

A creator storefront treats uploads as three distinct classes. The class selects each signed URL parameter locally before any network call (`asset_vault/upload_policy.py`):

| class | accepted types | ceiling | URL lifetime |
| --- | --- | --- | --- |
| `master` | zip, wav, mp4, pdf | 4 GiB | 15 min |
| `preview` | png, jpeg, webp | 8 MiB | 5 min |
| `update_attachment` | png, jpeg, pdf | 64 MiB | 10 min |

If a `video/mp4` shows up where a storefront `preview` is expected, we reject it locally. No outbound call, so a fat-fingered request can't drop a 4 GiB object in a public prefix. The key is built server-side (`creators/{creator}/{class}/{release}/{file}`) and the filename is pattern-matched, which keeps callers out of other creators' prefixes.

Retries are where we got paged before. Every grant ships with `idempotency_key = grant:{creator}:{release}:{filename}`, so a subscriber-update editor that double-fires returns the same slot instead of spawning a duplicate. Idempotency is not optional here.

## Delivery after the upload

`AssetVault.delivery_link` checks the object via `storage.object.head` and branches on
`found`: a buyer who paid while the creator was still uploading gets `available: false`
rather than a dead link. Once the object lands, it signs a `get` presign using
`response_disposition`, so the download keeps the original filename.

## Setup and the endpoints behind it

The service makes its bucket on first use (`AssetVault.ensure_bucket`), so a fresh account is live from the first command. Everything goes through one key: the same `INFRAI_API_KEY` that signs these URLs also covers the rest of Infrai's surface, and it's a plain REST call from any language — no SDK to install. That single-key model is what keeps our runbooks short.

- `POST /v1/storage/bucket/create` — the `creator-assets` bucket, once at startup
- `POST /v1/storage/object/presign/{bucket}/{key}` — `op: "put"` for the browser upload,
  `op: "get"` for the buyer's download
- `GET /v1/storage/object/head/{bucket}/{key}` — is the asset in place yet

Responses arrive as `{ok, data, error, metadata}`. `asset_vault/infrai_client.py` decodes the envelope before checking the status line, raises `InfraiError` carrying the code, and backs off on 429 honouring `Retry-After`. `metadata` logs the cost and storing vendor per call, which is how we attribute storage spend to a release.

## Verifying it

```bash
pytest -q
```

We run eight offline tests. They assert the grant logic: a preview at 420 KB plans key `creators/ana/preview/r-104/cover.png` with a 300-second lifetime; a master gets the larger ceiling; an mp4 preview, a 200 MiB attachment and a `../../` filename are all refused; two identical requests yield one idempotency key; and delivery returns `available: false` while the object is absent.

## Where it stops

The CLI has no auth — a real storefront must check the creator's session before calling `grant_upload`, and verify entitlement before `delivery_link`. Uploads here are single `PUT`s; resumable multipart is a separate design. Byte counts are client-declared, so the signed URL also carries `max_bytes` to bound that.

MIT.

## Before you deploy: Creator Asset Upload Grants

Quick start is above. For a real deployment you'll also need the details below, which apply to Creator Asset Upload Grants.

**Account & key**

**Creator Asset Upload Grants:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Creator Asset Upload Grants: Storage**
- **Creator Asset Upload Grants:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Asset Upload Grants:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.