"""Projects API — create, open, save, list, delete .annotatex project files."""
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import require_token
from app.project import Project
from app.utils import load_recent_projects, add_recent_project, remove_recent_project

router = APIRouter(prefix="/api/projects", tags=["projects"])

# In-memory store of open projects: path -> Project
_open_projects: dict[str, Project] = {}


def _get_project(project_path: str) -> Project:
    if project_path not in _open_projects:
        raise HTTPException(status_code=404, detail=f"Project not open: {project_path}")
    return _open_projects[project_path]


# ── Recent projects ───────────────────────────────────────────────────────────

@router.get("/recent")
def list_recent(_token: str = Depends(require_token)):
    return load_recent_projects()


# ── Open / create / close ─────────────────────────────────────────────────────

class OpenProjectRequest(BaseModel):
    path: str  # absolute path to .annotatex file


@router.post("/open")
def open_project(req: OpenProjectRequest, _token: str = Depends(require_token)):
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
    save_path: str             # absolute path where .annotatex will be saved
    import_yolo_labels: bool = False
    coco_json_path: Optional[str] = None


@router.post("/create", status_code=201)
def create_project(req: CreateProjectRequest, _token: str = Depends(require_token)):
    if not os.path.isdir(req.image_folder):
        raise HTTPException(status_code=400, detail="image_folder does not exist.")

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
        p.save(req.save_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save project: {e}")

    _open_projects[req.save_path] = p
    add_recent_project(req.save_path)
    return _project_summary(p)


@router.delete("/close")
def close_project(path: str, _token: str = Depends(require_token)):
    _open_projects.pop(path, None)
    return {"closed": path}


# ── Project state ─────────────────────────────────────────────────────────────

@router.get("/")
def list_open_projects(_token: str = Depends(require_token)):
    return [_project_summary(p) for p in _open_projects.values()]


@router.get("/info")
def get_project_info(path: str, _token: str = Depends(require_token)):
    return _project_summary(_get_project(path))


# ── Save ─────────────────────────────────────────────────────────────────────

@router.post("/save")
def save_project(path: str, _token: str = Depends(require_token)):
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
def save_project_as(req: SaveAsRequest, _token: str = Depends(require_token)):
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
def list_images(path: str, _token: str = Depends(require_token)):
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
def get_image_file(path: str, filename: str, _token: str = Depends(require_token)):
    p = _get_project(path)
    img_path = p.image_path(filename)
    if not os.path.isfile(img_path):
        raise HTTPException(status_code=404, detail="Image file not found.")
    return FileResponse(img_path)


@router.delete("/images")
def delete_image(path: str, filename: str, _token: str = Depends(require_token)):
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
def rescan_images(path: str, _token: str = Depends(require_token)):
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
def list_classes(path: str, _token: str = Depends(require_token)):
    p = _get_project(path)
    return [
        {**c.to_dict(), "annotation_count": p.class_annotation_count(c.id)}
        for c in p.classes
    ]


@router.post("/classes", status_code=201)
def add_class(req: AddClassRequest, _token: str = Depends(require_token)):
    p = _get_project(req.path)
    c = p.add_class(req.name)
    return c.to_dict()


@router.delete("/classes")
def remove_class(req: RemoveClassRequest, _token: str = Depends(require_token)):
    p = _get_project(req.path)
    if not p.remove_class(req.cls_id):
        raise HTTPException(status_code=404, detail="Class not found.")
    p.invalidate_annotated_count()
    return {"removed": req.cls_id}


@router.patch("/classes")
def update_class(req: UpdateClassRequest, _token: str = Depends(require_token)):
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
def get_project_settings(path: str, _token: str = Depends(require_token)):
    return _get_project(path).settings


@router.patch("/settings")
def update_project_settings(path: str, settings: dict, _token: str = Depends(require_token)):
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
