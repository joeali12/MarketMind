"""Durable upload-session mirror for serverless (/tmp is per-isolate).

When ``BLOB_READ_WRITE_TOKEN`` is set (Vercel Blob), every session write is
mirrored to private blob storage and missing local files are hydrated on read.
Local filesystem remains the working copy for pandas I/O.
"""

from __future__ import annotations

import json
import logging
import os
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
        # Sessions expire in hours; keep blob copies short-lived.
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


def hydrate_session_dir(session_id: str, directory: Path, *, extension: str | None = None) -> bool:
    """Restore session files from blob into ``directory``. Returns True if meta landed."""
    if not blob_enabled():
        return False
    meta_bytes = get_bytes(_pathname(session_id, "meta.json"))
    if not meta_bytes:
        return False
    directory.mkdir(parents=True, exist_ok=True)
    meta_path = directory / "meta.json"
    meta_path.write_bytes(meta_bytes)
    ext = extension
    if not ext:
        try:
            ext = str(json.loads(meta_bytes.decode("utf-8")).get("extension") or "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            ext = ""
    if ext:
        upload_name = f"upload{ext}"
        data = get_bytes(_pathname(session_id, upload_name))
        if data is not None:
            (directory / upload_name).write_bytes(data)
        bak_name = f"{upload_name}.pre_transform.bak"
        bak = get_bytes(_pathname(session_id, bak_name))
        if bak is not None:
            (directory / bak_name).write_bytes(bak)
    logger.info("blob_hydrate session_id_prefix=%s", session_id[:8])
    return True


def discard_session_blobs(session_id: str, *, extension: str | None = None) -> None:
    if not blob_enabled():
        return
    names = ["meta.json"]
    if extension:
        names.append(f"upload{extension}")
        names.append(f"upload{extension}.pre_transform.bak")
    else:
        # Best-effort common extensions when meta already gone locally.
        for ext in (".csv", ".xlsx"):
            names.append(f"upload{ext}")
            names.append(f"upload{ext}.pre_transform.bak")
    delete_pathnames([_pathname(session_id, n) for n in names])
