"""Filesystem browse endpoint — lets the frontend navigate the server's filesystem."""
from typing import Dict, Optional, Set
import os
from fastapi import APIRouter, Depends, HTTPException
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
    files: list[str] = []

    for entry in sorted(entries, key=lambda e: (not e.is_dir(), e.name.lower())):
        if entry.name.startswith("."):
            continue
        if entry.is_dir(follow_symlinks=False):
            dirs.append(entry.name)
        elif allowed_exts is not None:
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in allowed_exts:
                files.append(entry.name)

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
