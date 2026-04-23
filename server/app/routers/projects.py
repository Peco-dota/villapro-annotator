"""Projects API — create, open, save, list, delete .annotatex project files.

Projects are stored per-user at:
    ~/visionq-projects/<username>/<project_name>.annotatex

Admins can pass ?all=true to list_recent to see all users' projects.
"""
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import require_user
from app.project import Project
from app.utils import load_recent_projects, add_recent_project, remove_recent_project

router = APIRouter(prefix="/api/projects", tags=["projects"])

# In-memory store of open projects: path -> Project
_open_projects: dict[str, Project] = {}

PROJECTS_ROOT = Path.home() / "visionq-projects"


def _user_projects_dir(username: str) -> Path:
    d = PROJECTS_ROOT / username
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_project(project_path: str) -> Project:
    if project_path not in _open_projects:
        # Auto-load from disk if not currently open
        if not os.path.isfile(project_path):
            raise HTTPException(status_code=404, detail=f"Project file not found: {project_path}")
        try:
            p = Project.load(project_path)
            _open_projects[project_path] = p
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load project: {e}")
    return _open_projects[project_path]


# ── Recent projects ───────────────────────────────────────────────────────────

@router.get("/recent")
def list_recent(
    show_all: bool = Query(False, alias="all"),
    current_user: dict = Depends(require_user),
):
    paths = load_recent_projects()
    result = []
    for path in paths:
        if not os.path.isfile(path):
            continue

        # Filter by user unless admin requested all
        if not show_all or current_user["role"] != "admin":
            user_dir = str(_user_projects_dir(current_user["username"]))
            if not path.startswith(user_dir):
                continue

        if path in _open_projects:
            p = _open_projects[path]
            result.append(_project_summary(p))
        else:
            try:
                p = Project.load(path)
                result.append(_project_summary(p))
            except Exception:
                result.append({
                    "path": path,
                    "name": os.path.splitext(os.path.basename(path))[0],
                    "image_folder": "",
                    "total_images": 0,
                    "annotated_images": 0,
                    "total_boxes": 0,
                    "classes": [],
                    "current_index": 0,
                    "modified": False,
                    "settings": {},
                })
    return result


# ── Open / create / close ─────────────────────────────────────────────────────

class OpenProjectRequest(BaseModel):
    path: str


@router.post("/open")
def open_project(req: OpenProjectRequest, _user: dict = Depends(require_user)):
    if not os.path.isfile(req.path):
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        p = Project.load(req.path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load project: {e}")
    _open_projects[req.path] = p
    add_recent_project(req.path)
    return _project_summary(p)


class CreateProjectRequest(BaseModel):
    name: str
    image_folder: str
    classes: list[str] = []
    save_path: Optional[str] = None   # if omitted, auto-saved to user's projects dir
    import_yolo_labels: bool = False
    coco_json_path: Optional[str] = None


@router.post("/create", status_code=201)
def create_project(req: CreateProjectRequest, current_user: dict = Depends(require_user)):
    if not os.path.isdir(req.image_folder):
        raise HTTPException(status_code=400, detail="image_folder does not exist.")

    # Determine save path
    if req.save_path:
        save_path = req.save_path
        # If user gave a directory, auto-name the file
        if os.path.isdir(save_path):
            save_path = os.path.join(save_path, req.name + ".annotatex")
    else:
        user_dir = _user_projects_dir(current_user["username"])
        save_path = str(user_dir / (req.name + ".annotatex"))

    p = Project()
    p.name = req.name
    p.image_folder = req.image_folder
    for cls_name in req.classes:
        p.add_class(cls_name)
    p.scan_images()

    if req.coco_json_path:
        if not os.path.isfile(req.coco_json_path):
            raise HTTPException(status_code=400, detail="coco_json_path not found.")
        p.load_coco_labels(req.coco_json_path)
    elif req.import_yolo_labels:
        p.load_yolo_labels()

    try:
        p.save(save_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save project: {e}")

    _open_projects[save_path] = p
    add_recent_project(save_path)
    return _project_summary(p)


@router.delete("/close")
def close_project(path: str, _user: dict = Depends(require_user)):
    _open_projects.pop(path, None)
    return {"closed": path}


@router.delete("/recent")
def remove_from_recent(path: str, _user: dict = Depends(require_user)):
    _open_projects.pop(path, None)
    remove_recent_project(path)
    return {"removed": path}


# ── Project state ─────────────────────────────────────────────────────────────

@router.get("/")
def list_open_projects(_user: dict = Depends(require_user)):
    return [_project_summary(p) for p in _open_projects.values()]


@router.get("/info")
def get_project_info(path: str, _user: dict = Depends(require_user)):
    return _project_summary(_get_project(path))


# ── Save ──────────────────────────────────────────────────────────────────────

@router.post("/save")
def save_project(path: str, _user: dict = Depends(require_user)):
    p = _get_project(path)
    try:
        p.save()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"saved": p.path}


class SaveAsRequest(BaseModel):
    path: str
    new_path: str


@router.post("/save-as")
def save_project_as(req: SaveAsRequest, _user: dict = Depends(require_user)):
    p = _get_project(req.path)
    try:
        p.save(req.new_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    _open_projects[req.new_path] = p
    add_recent_project(req.new_path)
    return {"saved": req.new_path}


# ── Images ────────────────────────────────────────────────────────────────────

@router.get("/images")
def list_images(path: str, _user: dict = Depends(require_user)):
    p = _get_project(path)
    return [
        {
            "filename": fn,
            "index": i,
            "box_count": p.annotations.get(fn).box_count if p.annotations.get(fn) else 0,
        }
        for i, fn in enumerate(p.images)
    ]


@router.get("/images/file")
def get_image_file(path: str, filename: str, _user: dict = Depends(require_user)):
    p = _get_project(path)
    img_path = p.image_path(filename)
    if not os.path.isfile(img_path):
        raise HTTPException(status_code=404, detail="Image file not found.")
    return FileResponse(img_path)


@router.delete("/images")
def delete_image(path: str, filename: str, _user: dict = Depends(require_user)):
    p = _get_project(path)
    img_path = p.image_path(filename)
    label_path = os.path.join(p.image_folder, Path(filename).stem + ".txt")

    if filename not in p.images:
        raise HTTPException(status_code=404, detail="Image not in project.")

    try:
        if os.path.isfile(img_path):
            os.remove(img_path)
        if os.path.isfile(label_path):
            os.remove(label_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    idx = p.images.index(filename)
    p.images.pop(idx)
    p.annotations.pop(filename, None)
    p.invalidate_annotated_count()
    p.current_index = max(0, min(p.current_index, len(p.images) - 1))
    p.modified = True
    return {"deleted": filename, "remaining": len(p.images)}


@router.post("/images/rescan")
def rescan_images(path: str, _user: dict = Depends(require_user)):
    p = _get_project(path)
    count = p.scan_images()
    p.invalidate_annotated_count()
    return {"count": count}


# ── Classes ───────────────────────────────────────────────────────────────────

class AddClassRequest(BaseModel):
    path: str
    name: str


class RemoveClassRequest(BaseModel):
    path: str
    cls_id: int


class UpdateClassRequest(BaseModel):
    path: str
    cls_id: int
    name: Optional[str] = None
    color: Optional[str] = None


@router.get("/classes")
def list_classes(path: str, _user: dict = Depends(require_user)):
    p = _get_project(path)
    return [
        {**c.to_dict(), "annotation_count": p.class_annotation_count(c.id)}
        for c in p.classes
    ]


@router.post("/classes", status_code=201)
def add_class(req: AddClassRequest, _user: dict = Depends(require_user)):
    p = _get_project(req.path)
    c = p.add_class(req.name)
    return c.to_dict()


@router.delete("/classes")
def remove_class(req: RemoveClassRequest, _user: dict = Depends(require_user)):
    p = _get_project(req.path)
    if not p.remove_class(req.cls_id):
        raise HTTPException(status_code=404, detail="Class not found.")
    p.invalidate_annotated_count()
    return {"removed": req.cls_id}


@router.patch("/classes")
def update_class(req: UpdateClassRequest, _user: dict = Depends(require_user)):
    p = _get_project(req.path)
    c = p.get_class(req.cls_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Class not found.")
    if req.name is not None:
        c.name = req.name
    if req.color is not None:
        c.color = req.color
    p.modified = True
    return c.to_dict()


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings")
def get_project_settings(path: str, _user: dict = Depends(require_user)):
    return _get_project(path).settings


@router.patch("/settings")
def update_project_settings(path: str, settings: dict, _user: dict = Depends(require_user)):
    p = _get_project(path)
    p.settings.update(settings)
    p.modified = True
    return p.settings


# ── Helpers ───────────────────────────────────────────────────────────────────

def _project_summary(p: Project) -> dict:
    return {
        "path": p.path,
        "name": p.name,
        "image_folder": p.image_folder,
        "total_images": p.total_count,
        "annotated_images": p.annotated_count,
        "total_boxes": p.total_box_count,
        "classes": [c.to_dict() for c in p.classes],
        "current_index": p.current_index,
        "modified": p.modified,
        "settings": p.settings,
    }
