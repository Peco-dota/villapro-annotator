"""Filesystem browse and upload endpoints."""
from typing import Dict, Optional, Set
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from app.auth import require_user

router = APIRouter(prefix="/api/fs", tags=["filesystem"])


@router.get("/home")
def get_home(_user: dict = Depends(require_user)):
    """Return the server's home directory — a safe starting point for the file picker."""
    return {"home": os.path.expanduser("~")}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
MODEL_EXTS = {".pt", ".pth", ".onnx"}
YAML_EXTS  = {".yaml", ".yml"}
JSON_EXTS  = {".json", ".annotatex"}
ALL_EXTS   = IMAGE_EXTS | VIDEO_EXTS | MODEL_EXTS | YAML_EXTS | JSON_EXTS

# filter name → set of extensions shown (None = directories only)
_FILTERS: Dict[str, Optional[Set[str]]] = {
    "any":        None,          # dirs + all known file types
    "project":    JSON_EXTS,     # .annotatex / .json
    "images_dir": None,          # directory picker
    "model":      MODEL_EXTS,    # .pt .pth .onnx
    "video":      VIDEO_EXTS,    # video files
    "yaml":       YAML_EXTS,     # data.yaml
    "dir":        None,          # directory only
}


def _video_duration(path: str) -> float | None:
    """Return video duration in seconds by reading the container header via cv2."""
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps > 0 and frames > 0:
            return round(frames / fps, 1)
    except Exception:
        pass
    return None


@router.get("/browse")
def browse(
    path: str = "/",
    filter: str = "any",
    _user: dict = Depends(require_user),
):
    """
    Browse a directory on the server filesystem.

    Returns:
      - cwd: the resolved absolute path that was listed
      - parent: parent directory (null if at root)
      - dirs: list of subdirectory names
      - files: list of matching filenames (filtered by `filter`)
    """
    # Resolve and validate path
    try:
        cwd = os.path.realpath(os.path.abspath(path))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path.")

    if not os.path.isdir(cwd):
        # If a file path was passed, browse its parent
        cwd = os.path.dirname(cwd)
        if not os.path.isdir(cwd):
            raise HTTPException(status_code=404, detail="Directory not found.")

    allowed_exts = _FILTERS.get(filter)  # None = dirs-only (no files listed)

    try:
        entries = os.scandir(cwd)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied.")

    dirs: list[str] = []
    files: list[dict] = []

    for entry in sorted(entries, key=lambda e: (not e.is_dir(), e.name.lower())):
        if entry.name.startswith("."):
            continue
        if entry.is_dir(follow_symlinks=False):
            dirs.append(entry.name)
        elif allowed_exts is not None:
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in allowed_exts:
                try:
                    st = entry.stat()
                    size = st.st_size
                    modified = st.st_mtime
                except OSError:
                    size = 0
                    modified = 0
                duration = _video_duration(entry.path) if ext in VIDEO_EXTS else None
                files.append({
                    "name": entry.name,
                    "size": size,
                    "modified": modified,
                    "duration": duration,
                })

    parent = str(os.path.dirname(cwd)) if cwd != os.path.dirname(cwd) else None

    return {
        "cwd": cwd,
        "parent": parent,
        "dirs": dirs,
        "files": files,
    }


class MkdirRequest(BaseModel):
    parent: str
    name: str


@router.post("/mkdir", status_code=201)
def mkdir(req: MkdirRequest, _user: dict = Depends(require_user)):
    """Create a new directory inside `parent`."""
    name = req.name.strip()
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid folder name.")
    parent = os.path.realpath(os.path.abspath(req.parent))
    if not os.path.isdir(parent):
        raise HTTPException(status_code=404, detail="Parent directory not found.")
    new_dir = os.path.join(parent, name)
    if os.path.exists(new_dir):
        raise HTTPException(status_code=409, detail="A folder with that name already exists.")
    try:
        os.makedirs(new_dir)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied.")
    return {"path": new_dir}


@router.post("/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    dest: str = Query(..., description="Destination directory on the server"),
    _user: dict = Depends(require_user),
):
    """Upload a file from the client to a server directory.

    Streams directly to disk — no full-file RAM load.
    If a file with the same name already exists the upload is saved as
    filename_1.ext, filename_2.ext, etc.
    """
    dest_dir = os.path.realpath(os.path.abspath(dest))

    try:
        os.makedirs(dest_dir, exist_ok=True)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied creating destination directory.")

    # Sanitise filename — strip path components supplied by the browser
    filename = os.path.basename(file.filename or "upload").strip()
    if not filename or filename in (".", ".."):
        filename = "upload"

    base, ext = os.path.splitext(filename)
    final_path = os.path.join(dest_dir, filename)
    counter = 1
    while os.path.exists(final_path):
        final_path = os.path.join(dest_dir, f"{base}_{counter}{ext}")
        counter += 1

    try:
        with open(final_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                out.write(chunk)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied writing file.")
    except Exception as exc:
        try:
            os.unlink(final_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")

    return {"path": final_path}
