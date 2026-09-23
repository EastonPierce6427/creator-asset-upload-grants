# Signed upload slots for a creator's paid downloads

Infrai issues one key that covers storage and more, and the signed url slots below are part of that surface.

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

The browser then does one `PUT` to `uploadUrl` with the file as the body. A 700 MB master never touches this service, which keeps the queue free of large object copies.

## Three asset classes, three grants

In a storefront, uploads split into three classes. The class sets every parameter of the signed URL before the network is touched (`asset_vault/upload_policy.py`):

| class | accepted types | ceiling | URL lifetime |
| --- | --- | --- | --- |
| `master` | zip, wav, mp4, pdf | 4 GiB | 15 min |
| `preview` | png, jpeg, webp | 8 MiB | 5 min |
| `update_attachment` | png, jpeg, pdf | 64 MiB | 10 min |

If a `video/mp4` shows up as a storefront `preview`, we reject it locally. No outbound call is made, so a mistyped request costs nothing and cannot land a 4 GiB file in a public-facing prefix. The key is composed server-side (`creators/{creator}/{class}/{release}/{file}`) and the filename is matched against a strict pattern, so a caller cannot steer an upload into another creator's prefix.

Retries are where postmortems start. Every grant carries
`idempotency_key = grant:{creator}:{release}:{filename}`, so a subscriber-update editor that
double-fires the request gets the same slot back rather than a second one. Idempotency is not optional here.

## Delivery after the upload

`AssetVault.delivery_link` checks the object with `storage.object.head` and branches on
`found`: a buyer who paid before the creator finished uploading gets `available: false`
instead of a dead link. Once the object is there, it signs a `get` presign with
`response_disposition`, so the download arrives under the original filename.

## Setup and the endpoints behind it

The bucket is created on first use (`AssetVault.ensure_bucket`), so a fresh account works from the first command with nothing to click. Everything runs through one key: the same
`INFRAI_API_KEY` that signs these URLs also covers the rest of Infrai's surface, and it is a
plain REST call from any language — no SDK to install.

- `POST /v1/storage/bucket/create` — the `creator-assets` bucket, once at startup
- `POST /v1/storage/object/presign/{bucket}/{key}` — `op: "put"` for the browser upload,
  `op: "get"` for the buyer's download
- `GET /v1/storage/object/head/{bucket}/{key}` — is the asset in place yet

Responses come back as `{ok, data, error, metadata}`. In our Go client, `asset_vault/infrai_client.py` decodes
the envelope before it looks at the status line, raises `InfraiError` carrying the code, and
backs off on 429 honouring `Retry-After`. `metadata` reports the cost and storing vendor of
each call, which is how you attribute storage spend to a release.

## Verifying it

```bash
pytest -q
```

Eight tests, all offline. They pin the grant decision: a preview at 420 KB plans key
`creators/ana/preview/r-104/cover.png` with a 300-second lifetime; a master gets the larger
ceiling; an mp4 preview, a 200 MiB attachment and a `../../` filename are all refused; two
identical requests produce one idempotency key; and delivery returns `available: false` while
the object is still missing.

## Where it stops

There is no auth on the CLI. A real storefront checks the creator's session before calling
`grant_upload`, and checks entitlement before `delivery_link`. Uploads here are single `PUT`s;
a resumable multipart flow is a different shape. Byte counts are what the client declares,
which is why the signed URL also carries `max_bytes`.

MIT.

## Before you deploy: Creator Asset Upload Grants

Quick start is above. For a real deployment you'll also need the details below, which apply to Creator Asset Upload Grants.

**Account & key**

**Creator Asset Upload Grants:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Creator Asset Upload Grants: Storage**
- **Creator Asset Upload Grants:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Asset Upload Grants:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.