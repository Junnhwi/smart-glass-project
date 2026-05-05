# Object Storage Key Contract

## Canonical Shape

Capture images use this object key shape:

```text
captures/{userId}/{yyyy}/{mm}/{dd}/{captureId}-{fileName}
```

Example:

```text
captures/user-1/2026/04/07/capture-001-smart-glass-photo.jpg
```

`api-server` generates this key during `POST /media/upload-authorizations` and also when a capture request does not provide an explicit `imageKey`. The generation path is centralized in `apps/api-server/src/modules/media/object_keys.py`.

## Normalization

Explicit `imageKey` values are normalized before they are passed to the worker or to the media access URL signer:

- surrounding whitespace is trimmed
- repeated `/` separators are collapsed
- `\` separators are converted to `/`

The following values are rejected:

- blank keys
- absolute URLs such as `https://...`
- absolute paths such as `/captures/...`
- path traversal segments such as `.` or `..`
- control characters

Capture registration applies one additional boundary: explicit capture keys must stay under the requesting user's canonical prefix:

```text
captures/{userId}/...
```

For example, a request with `userId=user-1` may pass `captures/user-1/photo.jpg`, but it may not pass `captures/user-2/photo.jpg` or `private/photo.jpg`.

## Ownership Boundary

Object keys identify storage objects, but they do not prove ownership by themselves.

`api-server` checks media ownership through memory records before issuing signed access URLs. The inference worker only receives the normalized object key and reads that object through its storage service boundary.

## Related Flow

- Upload authorization can pre-generate the canonical `sourceImage.imageKey` and a presigned PUT `uploadUrl`.
- Capture registration builds or normalizes `sourceImage.imageKey`.
- The worker payload uses the same `imageKey`.
- The worker reads the object from object storage.
- Memory records store the same `imageKey` for search, gallery, and media access URL lookup.
