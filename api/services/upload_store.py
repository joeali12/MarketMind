"""Temporary upload storage with size/type limits and TTL cleanup.

Logging policy: never log file contents, row values, or PII.
Log only: timestamp, session id hash, byte size, extension, outcome codes, row count.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, BinaryIO, Iterable

from api.settings import (
    ALLOWED_UPLOAD_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    UPLOAD_TMP_ROOT,
    UPLOAD_TTL_SECONDS,
)

logger = logging.getLogger("marketmind.upload")

# ISO-ish codes the UI may offer; never inferred from amounts.
KNOWN_CURRENCY_CODES = frozenset(
    {"GBP", "USD", "EUR", "EGP", "SAR", "AED", "CAD", "AUD", "OTHER", "UNSPECIFIED"}
)


@dataclass
class UploadSessionMeta:
    session_id: str
    created_at: float
    filename: str
    extension: str
    byte_size: int
    row_count: int | None = None
    has_category_mapped: bool = False
    category_column: str | None = None
    # User-selected; never inferred from numeric amounts.
    currency_code: str | None = None
    # dayfirst | monthfirst | iso | None (unset / needs confirmation when ambiguous)
    date_format: str | None = None
    date_format_confirmed: bool = False
    # User confirmed the assistant's file summary before gap-fill.
    profile_confirmed: bool = False
    # User preference after confirm: None | "manual" | "smart"
    gap_fill_preference: str | None = None
    # POS mapping: canonical field → source column name (session-scoped).
    column_mapping: dict | None = None
    mapping_confirmed: bool = False
    # Excel worksheet selection (required when workbook has multiple sheets).
    selected_sheet: str | None = None
    workbook_sheets: list | None = None
    # When a currency column has multiple codes, user must pick one for totals.
    analysis_currency_filter: str | None = None
    # Cleaning proposal ids the user accepted for this session (dashboard/export).
    accepted_cleaning_ids: list | None = None


def _session_dir(session_id: str) -> Path:
    return UPLOAD_TMP_ROOT / session_id


def _meta_path(session_id: str) -> Path:
    return _session_dir(session_id) / "meta.json"


def _file_path(session_id: str, extension: str) -> Path:
    return _session_dir(session_id) / f"upload{extension}"


def session_id_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]


def ensure_tmp_root() -> None:
    UPLOAD_TMP_ROOT.mkdir(parents=True, exist_ok=True)


def cleanup_expired(now: float | None = None) -> int:
    """Delete session dirs older than TTL. Returns number removed."""
    ensure_tmp_root()
    ts = now if now is not None else time.time()
    removed = 0
    for path in UPLOAD_TMP_ROOT.iterdir():
        if not path.is_dir():
            continue
        meta_file = path / "meta.json"
        created = path.stat().st_mtime
        if meta_file.exists():
            try:
                created = float(json.loads(meta_file.read_text()).get("created_at", created))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        if ts - created > UPLOAD_TTL_SECONDS:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
            logger.info(
                "upload_ttl_delete session_hash=%s age_s=%.0f",
                session_id_hash(path.name),
                ts - created,
            )
    return removed


def _validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(f"Allowed types: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}")
    return ext


def create_session(filename: str, content: bytes) -> UploadSessionMeta:
    """Create session from already-buffered bytes (tests / small helpers)."""
    ensure_tmp_root()
    cleanup_expired()
    ext = _validate_extension(filename)
    if len(content) > MAX_UPLOAD_BYTES:
        logger.info(
            "upload_reject session_hash=- reason=too_large bytes=%s",
            len(content),
        )
        raise ValueError(f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    if len(content) == 0:
        raise ValueError("Empty file")
    return _write_new_session(filename, ext, content)


def create_session_streaming(
    filename: str,
    chunks: Iterable[bytes],
    *,
    max_bytes: int | None = None,
) -> UploadSessionMeta:
    """Write upload while streaming; abort as soon as max_bytes is exceeded.

    Does not require the full payload in memory before the size check.
    """
    ensure_tmp_root()
    cleanup_expired()
    ext = _validate_extension(filename)
    limit = MAX_UPLOAD_BYTES if max_bytes is None else max_bytes

    sid = str(uuid.uuid4())
    directory = _session_dir(sid)
    directory.mkdir(parents=True, exist_ok=False)
    dest = _file_path(sid, ext)
    total = 0
    try:
        with dest.open("wb") as fh:
            for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > limit:
                    logger.info(
                        "upload_reject session_hash=%s reason=too_large bytes=%s",
                        session_id_hash(sid),
                        total,
                    )
                    raise ValueError(f"File exceeds {limit // (1024 * 1024)} MB limit")
                fh.write(chunk)
        if total == 0:
            raise ValueError("Empty file")
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise

    meta = UploadSessionMeta(
        session_id=sid,
        created_at=time.time(),
        filename=Path(filename).name,
        extension=ext,
        byte_size=total,
    )
    _meta_path(sid).write_text(json.dumps(asdict(meta)))
    logger.info(
        "upload_stored session_hash=%s bytes=%s ext=%s",
        session_id_hash(sid),
        meta.byte_size,
        ext,
    )
    return meta


def create_session_from_fileobj(
    filename: str,
    fileobj: BinaryIO,
    *,
    chunk_size: int = 1024 * 1024,
    max_bytes: int | None = None,
) -> UploadSessionMeta:
    def _iter() -> Iterable[bytes]:
        while True:
            block = fileobj.read(chunk_size)
            if not block:
                break
            yield block

    return create_session_streaming(filename, _iter(), max_bytes=max_bytes)


async def create_session_from_upload_file(
    filename: str,
    read_chunk,
    *,
    chunk_size: int = 1024 * 1024,
    max_bytes: int | None = None,
) -> UploadSessionMeta:
    """Async streaming write: size limit enforced per chunk before continuing."""
    ensure_tmp_root()
    cleanup_expired()
    ext = _validate_extension(filename)
    limit = MAX_UPLOAD_BYTES if max_bytes is None else max_bytes

    sid = str(uuid.uuid4())
    directory = _session_dir(sid)
    directory.mkdir(parents=True, exist_ok=False)
    dest = _file_path(sid, ext)
    total = 0
    try:
        with dest.open("wb") as fh:
            while True:
                block = await read_chunk(chunk_size)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    logger.info(
                        "upload_reject session_hash=%s reason=too_large bytes=%s",
                        session_id_hash(sid),
                        total,
                    )
                    raise ValueError(f"File exceeds {limit // (1024 * 1024)} MB limit")
                fh.write(block)
        if total == 0:
            raise ValueError("Empty file")
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise

    meta = UploadSessionMeta(
        session_id=sid,
        created_at=time.time(),
        filename=Path(filename).name,
        extension=ext,
        byte_size=total,
    )
    _meta_path(sid).write_text(json.dumps(asdict(meta)))
    logger.info(
        "upload_stored session_hash=%s bytes=%s ext=%s",
        session_id_hash(sid),
        meta.byte_size,
        ext,
    )
    return meta


def _write_new_session(filename: str, ext: str, content: bytes) -> UploadSessionMeta:
    sid = str(uuid.uuid4())
    directory = _session_dir(sid)
    directory.mkdir(parents=True, exist_ok=False)
    dest = _file_path(sid, ext)
    dest.write_bytes(content)
    meta = UploadSessionMeta(
        session_id=sid,
        created_at=time.time(),
        filename=Path(filename).name,
        extension=ext,
        byte_size=len(content),
    )
    _meta_path(sid).write_text(json.dumps(asdict(meta)))
    logger.info(
        "upload_stored session_hash=%s bytes=%s ext=%s",
        session_id_hash(sid),
        meta.byte_size,
        ext,
    )
    return meta


def load_meta(session_id: str) -> UploadSessionMeta:
    path = _meta_path(session_id)
    if not path.exists():
        raise FileNotFoundError("Upload session not found or expired")
    data = json.loads(path.read_text())
    allowed = {f.name for f in fields(UploadSessionMeta)}
    filtered = {k: v for k, v in data.items() if k in allowed}
    return UploadSessionMeta(**filtered)


def save_meta(meta: UploadSessionMeta) -> None:
    _meta_path(meta.session_id).write_text(json.dumps(asdict(meta)))


def upload_path(session_id: str) -> Path:
    meta = load_meta(session_id)
    path = _file_path(session_id, meta.extension)
    if not path.exists():
        raise FileNotFoundError("Upload file missing")
    return path


def discard_session(session_id: str) -> None:
    directory = _session_dir(session_id)
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
        logger.info("upload_discard session_hash=%s", session_id_hash(session_id))


def write_export(session_id: str, content: bytes, name: str = "cleaned.csv") -> Path:
    directory = _session_dir(session_id)
    if not directory.exists():
        raise FileNotFoundError("Upload session not found or expired")
    out = directory / name
    out.write_bytes(content)
    return out


def currency_label(meta: UploadSessionMeta) -> str:
    """Human label for UI — never default uploaded amounts to GBP."""
    if not meta.currency_code or meta.currency_code == "UNSPECIFIED":
        return "source currency (not selected)"
    if meta.currency_code == "OTHER":
        return "other (user-selected)"
    return meta.currency_code


def safe_log_outcome(
    session_id: str | None,
    *,
    outcome: str,
    row_count: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "outcome": outcome,
        "session_hash": session_id_hash(session_id) if session_id else "-",
        "row_count": row_count,
    }
    if extra:
        for k, v in extra.items():
            if k in {"missing_columns", "code", "proposals", "accepted", "currency", "date_format"}:
                payload[k] = v
    logger.info("upload_outcome %s", payload)
