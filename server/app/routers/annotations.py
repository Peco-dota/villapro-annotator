"""Annotation API — bounding boxes per image."""
import copy
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_user
from app.annotation import BoundingBox
from app.routers.projects import _get_project

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


# ── Box CRUD ──────────────────────────────────────────────────────────────────

@router.get("/")
def get_annotations(project_path: str, filename: str, _user: dict = Depends(require_user)):
    p = _get_project(project_path)
    ia = p.annotations.get(filename)
    if ia is None:
        return {"filename": filename, "boxes": []}
    return {"filename": filename, "boxes": [b.to_dict() for b in ia.boxes]}


class BoxCreateRequest(BaseModel):
    project_path: str
    filename: str
    class_id: int
    cx: float
    cy: float
    w: float
    h: float


class BoxUpdateRequest(BaseModel):
    project_path: str
    filename: str
    box_id: str
    class_id: Optional[int] = None
    cx: Optional[float] = None
    cy: Optional[float] = None
    w: Optional[float] = None
    h: Optional[float] = None


class BoxDeleteRequest(BaseModel):
    project_path: str
    filename: str
    box_id: str


class BoxesReplaceRequest(BaseModel):
    project_path: str
    filename: str
    boxes: list[dict]


@router.post("/", status_code=201)
def add_box(req: BoxCreateRequest, _user: dict = Depends(require_user)):
    p = _get_project(req.project_path)
    if req.filename not in p.images:
        raise HTTPException(status_code=404, detail="Image not in project.")

    box = BoundingBox(
        class_id=req.class_id,
        cx=req.cx, cy=req.cy,
        w=req.w, h=req.h,
    )
    if not box.is_valid():
        raise HTTPException(status_code=400, detail="Invalid bounding box coordinates.")

    from app.project import ImageAnnotation
    ia = p.annotations.setdefault(req.filename, ImageAnnotation(filename=req.filename))
    ia.boxes.append(box)
    p.modified = True
    p.invalidate_annotated_count()
    return box.to_dict()


@router.patch("/")
def update_box(req: BoxUpdateRequest, _user: dict = Depends(require_user)):
    p = _get_project(req.project_path)
    ia = p.annotations.get(req.filename)
    if ia is None:
        raise HTTPException(status_code=404, detail="No annotations for this image.")

    box = next((b for b in ia.boxes if b.id == req.box_id), None)
    if box is None:
        raise HTTPException(status_code=404, detail="Box not found.")

    if req.class_id is not None:
        box.class_id = req.class_id
    if req.cx is not None:
        box.cx = req.cx
    if req.cy is not None:
        box.cy = req.cy
    if req.w is not None:
        box.w = req.w
    if req.h is not None:
        box.h = req.h

    p.modified = True
    return box.to_dict()


@router.delete("/")
def delete_box(req: BoxDeleteRequest, _user: dict = Depends(require_user)):
    p = _get_project(req.project_path)
    ia = p.annotations.get(req.filename)
    if ia is None:
        raise HTTPException(status_code=404, detail="No annotations for this image.")

    before = len(ia.boxes)
    ia.boxes = [b for b in ia.boxes if b.id != req.box_id]
    if len(ia.boxes) == before:
        raise HTTPException(status_code=404, detail="Box not found.")

    p.modified = True
    p.invalidate_annotated_count()
    return {"deleted": req.box_id}


@router.put("/replace")
def replace_boxes(req: BoxesReplaceRequest, _user: dict = Depends(require_user)):
    """Replace ALL boxes for an image in one call (used by canvas after drag/resize)."""
    p = _get_project(req.project_path)
    if req.filename not in p.images:
        raise HTTPException(status_code=404, detail="Image not in project.")

    from app.project import ImageAnnotation
    boxes = [BoundingBox.from_dict(b) for b in req.boxes]
    invalid = [b for b in boxes if not b.is_valid()]
    if invalid:
        raise HTTPException(status_code=400, detail=f"{len(invalid)} invalid box(es) in request.")

    ia = p.annotations.setdefault(req.filename, ImageAnnotation(filename=req.filename))
    ia.boxes = boxes
    p.modified = True
    p.invalidate_annotated_count()
    return {"filename": req.filename, "boxes": [b.to_dict() for b in ia.boxes]}


@router.post("/copy-from-prev")
def copy_boxes_from_prev(project_path: str, filename: str, _user: dict = Depends(require_user)):
    """Copy all boxes from the previous image to the given image."""
    p = _get_project(project_path)
    if filename not in p.images:
        raise HTTPException(status_code=404, detail="Image not in project.")

    idx = p.images.index(filename)
    if idx == 0:
        raise HTTPException(status_code=400, detail="No previous image to copy from.")

    prev_fn = p.images[idx - 1]
    prev_ia = p.annotations.get(prev_fn)
    if not prev_ia or not prev_ia.boxes:
        return {"filename": filename, "boxes": [], "copied": 0}

    from app.project import ImageAnnotation
    new_boxes = copy.deepcopy(prev_ia.boxes)
    ia = p.annotations.setdefault(filename, ImageAnnotation(filename=filename))
    ia.boxes = new_boxes
    p.modified = True
    p.invalidate_annotated_count()
    return {"filename": filename, "boxes": [b.to_dict() for b in ia.boxes], "copied": len(new_boxes)}


@router.post("/navigate")
def set_current_index(project_path: str, index: int, _user: dict = Depends(require_user)):
    """Set which image is 'current' in the project (for auto-save tracking)."""
    p = _get_project(project_path)
    if index < 0 or index >= len(p.images):
        raise HTTPException(status_code=400, detail="Index out of range.")
    p.current_index = index
    fn = p.images[index]
    ia = p.annotations.get(fn)
    return {
        "index": index,
        "filename": fn,
        "boxes": [b.to_dict() for b in ia.boxes] if ia else [],
    }
