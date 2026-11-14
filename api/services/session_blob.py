"""Durable upload-session mirror for serverless (/tmp is per-isolate).

When ``BLOB_READ_WRITE_TOKEN`` is set (Vercel Blob), every session write is
mirrored to private blob storage and missing/stale local files are hydrated on
read. Local filesystem remains the working copy for pandas I/O.

Blob copies honor ``UPLOAD_TTL_SECONDS`` (not only the store's day-scale TTL).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("marketmind.upload.blob")

_API = "https://vercel.com/api/blob"
_API_VERSION = "13"
_PREFIX = "mm-uploads"


def blob_enabled() -> bool:
    return bool((os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip())


def _token() -> str:
    return (os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip()


def _store_id(token: str) -> str:
    # vercel_blob_rw_<STOREID>_<secret>
    parts = token.split("_")
    if len(parts) >= 4:
        return parts[3]
    return ""


def _blob_url(store_id: str, pathname: str) -> str:
    return f"https://{store_id.lower()}.private.blob.vercel-storage.com/{pathname}"


def _pathname(session_id: str, name: str) -> str:
    return f"{_PREFIX}/{session_id}/{name}"


def _session_file_names(extension: str) -> list[str]:
    ext = extension or ""
    return [
        f"upload{ext}",
        f"upload{ext}.pre_transform.bak",
        f"upload{ext}.pre_safe_fill.bak",
    ]


def _headers(
    token: str,
    *,
    access: str | None = None,
    content_type: str | None = None,
    allow_overwrite: bool = True,
) -> dict[str, str]:
    store = _store_id(token)
    h = {
        "Authorization": f"Bearer {token}",
        "x-api-version": _API_VERSION,
        "x-vercel-blob-store-id": store,
        "x-api-blob-request-attempt": "0",
    }
    if access:
        h["x-vercel-blob-access"] = access
        h["x-add-random-suffix"] = "0"
        h["x-allow-overwrite"] = "1" if allow_overwrite else "0"
        # Store-level ceiling; app TTL is enforced on hydrate via created_at.
        h["x-ttl-days"] = "1"
    if content_type:
        h["x-content-type"] = content_type
    return h


def put_bytes(pathname: str, data: bytes, *, content_type: str) -> dict[str, Any] | None:
    token = _token()
    if not token:
        return None
    qs = urllib.parse.urlencode({"pathname": pathname})
    req = urllib.request.Request(
        f"{_API}?{qs}",
        data=data,
        method="PUT",
        headers=_headers(
            token,
            access="private",
            content_type=content_type,
            allow_overwrite=True,
        ),
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        logger.warning(
            "blob_put_failed pathname=%s status=%s detail=%s",
            pathname,
            exc.code,
            detail,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("blob_put_failed pathname=%s err=%s", pathname, type(exc).__name__)
        return None


def get_bytes(pathname: str) -> bytes | None:
    token = _token()
    if not token:
        return None
    store = _store_id(token)
    if not store:
        return None
    url = _blob_url(store, pathname)
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            logger.warning(
                "blob_get_failed pathname=%s status=%s", pathname, exc.code
            )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("blob_get_failed pathname=%s err=%s", pathname, type(exc).__name__)
        return None


def delete_pathnames(pathnames: list[str]) -> None:
    token = _token()
    if not token or not pathnames:
        return
    store = _store_id(token)
    urls = [_blob_url(store, p) for p in pathnames]
    payload = json.dumps({"urls": urls}).encode("utf-8")
    req = urllib.request.Request(
        f"{_API}/delete",
        data=payload,
        method="POST",
        headers={
            **_headers(token),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except Exception as exc:  # noqa: BLE001
        logger.warning("blob_delete_failed err=%s", type(exc).__name__)


def sync_session_dir(session_id: str, directory: Path) -> None:
    """Push every file in the local session directory to blob."""
    if not blob_enabled() or not directory.is_dir():
        return
    for path in directory.iterdir():
        if not path.is_file():
            continue
        ctype = "application/json" if path.suffix == ".json" else "application/octet-stream"
        put_bytes(_pathname(session_id, path.name), path.read_bytes(), content_type=ctype)


def _meta_expired(meta: dict[str, Any], *, now: float | None = None) -> bool:
    from api.settings import UPLOAD_TTL_SECONDS

    ts = now if now is not None else time.time()
    try:
        created = float(meta.get("created_at") or 0)
    except (TypeError, ValueError):
        created = 0.0
    if created <= 0:
        return True
    return (ts - created) > UPLOAD_TTL_SECONDS


def hydrate_session_dir(
    session_id: str,
    directory: Path,
    *,
    extension: str | None = None,
    force: bool = False,
) -> str:
    """Restore session files from blob into ``directory``.

    Returns a status string:
    - ``ok`` — non-expired meta applied (or local kept as newer)
    - ``expired`` — blob meta past TTL; blob discarded
    - ``missing`` — no blob meta (404 / never mirrored)
    - ``error`` — transport/parse failure; caller must keep local
    - ``disabled`` — blob not configured
    """
    if not blob_enabled():
        return "disabled"
    meta_bytes = get_bytes(_pathname(session_id, "meta.json"))
    if not meta_bytes:
        # Distinguish "never stored" from "GET failed" is hard via get_bytes;
        # treat empty as missing — never instruct callers to wipe local.
        return "missing"
    try:
        meta_obj = json.loads(meta_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "error"
    if not isinstance(meta_obj, dict):
        return "error"
    if _meta_expired(meta_obj):
        discard_session_blobs(
            session_id, extension=str(meta_obj.get("extension") or extension or "") or None
        )
        logger.info("blob_hydrate_expired session_id_prefix=%s", session_id[:8])
        return "expired"

    directory.mkdir(parents=True, exist_ok=True)
    meta_path = directory / "meta.json"
    refresh = force or not meta_path.exists()
    if meta_path.exists() and meta_path.read_bytes() != meta_bytes:
        try:
            local_obj = json.loads(meta_path.read_text())
            local_u = float(
                local_obj.get("updated_at") or local_obj.get("created_at") or 0
            )
            blob_u = float(
                meta_obj.get("updated_at") or meta_obj.get("created_at") or 0
            )
            # Prefer the newer copy so a just-written pending_transform is not
            # clobbered by a slightly stale blob read on the same isolate.
            refresh = blob_u > local_u
        except (json.JSONDecodeError, TypeError, ValueError):
            refresh = True
    if refresh:
        meta_path.write_bytes(meta_bytes)

    ext = extension or str(meta_obj.get("extension") or "")
    if ext:
        for name in _session_file_names(ext):
            dest = directory / name
            if not refresh and dest.exists():
                continue
            data = get_bytes(_pathname(session_id, name))
            if data is not None:
                dest.write_bytes(data)
    logger.info("blob_hydrate session_id_prefix=%s", session_id[:8])
    return "ok"


def discard_session_blobs(session_id: str, *, extension: str | None = None) -> None:
    if not blob_enabled():
        return
    names = ["meta.json"]
    if extension:
        names.extend(_session_file_names(extension))
    else:
        for ext in (".csv", ".xlsx"):
            names.extend(_session_file_names(ext))
    # Unique while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    delete_pathnames([_pathname(session_id, n) for n in ordered])
