"""Debug logs API — list, download, and delete direction-debug CSV files."""
import glob
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.auth import require_user

router = APIRouter(prefix="/api/debug-logs", tags=["debug-logs"])

_DEFAULT_DEBUG_DIR = "/villapro-data/debug"
_DATA_DEBUG_DIR = os.path.join(os.environ.get("VISIONQ_DATA", "/data"), "debug")


def _collect_dirs() -> set[str]:
    dirs: set[str] = {_DEFAULT_DEBUG_DIR, _DATA_DEBUG_DIR}
    return dirs


def _is_safe_csv(path: str) -> bool:
    abs_path = os.path.realpath(os.path.abspath(path))
    return abs_path.lower().endswith(".csv") and os.path.isfile(abs_path)


@router.get("")
def list_debug_logs(_user: dict = Depends(require_user)):
    """Return all .csv debug files found across all debug directories."""
    base_dirs = _collect_dirs()
    seen: set[str] = set()
    results = []
    for base in base_dirs:
        norm_base = os.path.normpath(base)
        if not os.path.isdir(norm_base):
            continue
        for csv in glob.glob(os.path.join(norm_base, "**", "*.csv"), recursive=True):
            abs_csv = os.path.normpath(csv)
            if abs_csv in seen:
                continue
            seen.add(abs_csv)
            try:
                stat = os.stat(abs_csv)
                parent = os.path.dirname(abs_csv)
                service = os.path.basename(parent) if os.path.normpath(parent) != norm_base else "other"
                results.append({
                    "path": abs_csv,
                    "filename": os.path.basename(abs_csv),
                    "service": service,
                    "size_bytes": stat.st_size,
                    "created_at": stat.st_mtime,
                })
            except OSError:
                pass
    results.sort(key=lambda r: r["created_at"], reverse=True)
    return results


@router.get("/download")
def download_debug_log(
    path: str = Query(...),
    token: Optional[str] = None,
    _user: dict = Depends(require_user),
):
    """Stream a debug CSV file as an attachment download."""
    if not _is_safe_csv(path):
        raise HTTPException(status_code=404, detail="Debug log not found.")
    abs_path = os.path.realpath(os.path.abspath(path))
    return FileResponse(
        abs_path,
        media_type="text/csv",
        filename=os.path.basename(abs_path),
        headers={"Content-Disposition": f'attachment; filename="{os.path.basename(abs_path)}"'},
    )


@router.delete("")
def delete_debug_log(
    path: str = Query(...),
    _user: dict = Depends(require_user),
):
    """Permanently delete a debug log file."""
    if not _is_safe_csv(path):
        raise HTTPException(status_code=404, detail="Debug log not found.")
    abs_path = os.path.realpath(os.path.abspath(path))
    try:
        os.unlink(abs_path)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied.")
    return {"deleted": abs_path}
