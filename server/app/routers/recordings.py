"""Recordings management API — list, download, and delete recorded video files."""
import glob
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.auth import require_user
from app.detection_service import get_registry

router = APIRouter(prefix="/api/recordings", tags=["recordings"])

_DEFAULT_RECORD_DIR = "/villapro-data/recordings"
_DATA_RECORD_DIR = os.path.join(os.environ.get("VISIONQ_DATA", "/data"), "recordings")

# Extra dirs to always scan (handles legacy typo in folder name)
_EXTRA_SCAN_DIRS = ["/villapro-data/recodings"]


def _collect_dirs() -> set[str]:
    """Return all directories that may contain recordings."""
    dirs: set[str] = {_DEFAULT_RECORD_DIR, _DATA_RECORD_DIR, *_EXTRA_SCAN_DIRS}
    for cfg in get_registry().get_configs():
        if cfg.record_dir:
            dirs.add(cfg.record_dir)
    return dirs


def _is_safe_mp4(path: str) -> bool:
    abs_path = os.path.realpath(os.path.abspath(path))
    if not (abs_path.lower().endswith(".mp4") and os.path.isfile(abs_path)):
        return False
    allowed = {os.path.realpath(d) for d in _collect_dirs() if os.path.isdir(d)}
    return any(abs_path.startswith(d + os.sep) for d in allowed)


@router.get("")
def list_recordings(_user: dict = Depends(require_user)):
    """Return all .mp4 recording files found across all configured recording directories."""
    base_dirs = _collect_dirs()
    seen: set[str] = set()
    results = []
    for base in base_dirs:
        norm_base = os.path.normpath(base)
        if not os.path.isdir(norm_base):
            continue
        for mp4 in glob.glob(os.path.join(norm_base, "**", "*.mp4"), recursive=True):
            abs_mp4 = os.path.normpath(mp4)
            if abs_mp4 in seen:
                continue
            seen.add(abs_mp4)
            try:
                stat = os.stat(abs_mp4)
                parent = os.path.dirname(abs_mp4)
                # If the file sits directly in a base recordings dir, label it "other"
                service = os.path.basename(parent) if os.path.normpath(parent) != norm_base else "other"
                results.append({
                    "path": abs_mp4,
                    "filename": os.path.basename(abs_mp4),
                    "service": service,
                    "size_bytes": stat.st_size,
                    "created_at": stat.st_mtime,
                })
            except OSError:
                pass
    results.sort(key=lambda r: r["created_at"], reverse=True)
    return results


@router.get("/download")
def download_recording(
    path: str = Query(...),
    token: Optional[str] = None,
    _user: dict = Depends(require_user),
):
    """Stream a recording file as an attachment download."""
    if not _is_safe_mp4(path):
        raise HTTPException(status_code=404, detail="Recording not found.")
    abs_path = os.path.realpath(os.path.abspath(path))
    return FileResponse(
        abs_path,
        media_type="video/mp4",
        filename=os.path.basename(abs_path),
        headers={"Content-Disposition": f'attachment; filename="{os.path.basename(abs_path)}"'},
    )


@router.delete("")
def delete_recording(
    path: str = Query(...),
    _user: dict = Depends(require_user),
):
    """Permanently delete a recording file."""
    if not _is_safe_mp4(path):
        raise HTTPException(status_code=404, detail="Recording not found.")
    abs_path = os.path.realpath(os.path.abspath(path))
    try:
        os.unlink(abs_path)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied.")
    return {"deleted": abs_path}
