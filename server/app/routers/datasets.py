"""Dataset operations — export, augmentation, split, batch export, training."""
import os
import threading
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.auth import require_token
from app.augmentation import AugConfig, run_augmentation, augment_from_folder
from app.utils import export_yolo, export_coco, batch_export_yolo, split_dataset
from app.routers.projects import _get_project

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# Simple job tracker for long-running operations
_jobs: dict[str, dict] = {}  # job_id -> {status, result, error}


def _new_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    return job_id


def _job_done(job_id: str, result: dict):
    _jobs[job_id] = {"status": "done", "result": result, "error": None}


def _job_failed(job_id: str, error: str):
    _jobs[job_id] = {"status": "failed", "result": None, "error": error}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _token: str = Depends(require_token)):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job_id": job_id, **job}


# ── YOLO Export ───────────────────────────────────────────────────────────────

class ExportYoloRequest(BaseModel):
    project_path: str
    output_dir: str
    split: Optional[dict] = None   # e.g. {"train": 0.8, "val": 0.1, "test": 0.1}
    generate_yaml: bool = True


@router.post("/export/yolo")
def export_yolo_endpoint(req: ExportYoloRequest, background_tasks: BackgroundTasks,
                         _token: str = Depends(require_token)):
    p = _get_project(req.project_path)
    job_id = _new_job()

    def _run():
        try:
            stats = export_yolo(p, req.output_dir, req.split, req.generate_yaml)
            _job_done(job_id, stats)
        except Exception as e:
            _job_failed(job_id, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job_id}


# ── COCO Export ───────────────────────────────────────────────────────────────

class ExportCocoRequest(BaseModel):
    project_path: str
    output_dir: str


@router.post("/export/coco")
def export_coco_endpoint(req: ExportCocoRequest, background_tasks: BackgroundTasks,
                         _token: str = Depends(require_token)):
    p = _get_project(req.project_path)
    job_id = _new_job()

    def _run():
        try:
            stats = export_coco(p, req.output_dir)
            _job_done(job_id, stats)
        except Exception as e:
            _job_failed(job_id, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job_id}


# ── Batch (multi-project) YOLO Export ────────────────────────────────────────

class BatchExportRequest(BaseModel):
    project_paths: list[str]
    output_dir: str
    split: Optional[dict] = None
    generate_yaml: bool = True
    augmentation: Optional[dict] = None  # AugConfig fields as dict, or null


@router.post("/export/batch")
def batch_export_endpoint(req: BatchExportRequest, background_tasks: BackgroundTasks,
                          _token: str = Depends(require_token)):
    for path in req.project_paths:
        if not os.path.isfile(path):
            raise HTTPException(status_code=400, detail=f"Project not found: {path}")

    aug_cfg = None
    if req.augmentation:
        aug_cfg = AugConfig(**req.augmentation)

    job_id = _new_job()

    def _run():
        try:
            stats = batch_export_yolo(
                req.project_paths, req.output_dir,
                req.split, req.generate_yaml, aug_cfg,
            )
            _job_done(job_id, stats)
        except Exception as e:
            _job_failed(job_id, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job_id}


# ── Dataset split ─────────────────────────────────────────────────────────────

class SplitRequest(BaseModel):
    folder: str
    split: dict   # {"train": 0.8, "val": 0.1, "test": 0.1}
    generate_yaml: bool = True


@router.post("/split")
def split_dataset_endpoint(req: SplitRequest, background_tasks: BackgroundTasks,
                           _token: str = Depends(require_token)):
    if not os.path.isdir(req.folder):
        raise HTTPException(status_code=400, detail="Folder not found.")

    job_id = _new_job()

    def _run():
        try:
            stats = split_dataset(req.folder, req.split, req.generate_yaml)
            _job_done(job_id, stats)
        except Exception as e:
            _job_failed(job_id, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job_id}


# ── Augmentation ──────────────────────────────────────────────────────────────

class AugmentProjectRequest(BaseModel):
    project_path: str
    output_dir: str
    flip_horizontal: bool = True
    flip_vertical: bool = False
    brightness: bool = True
    brightness_range: list[float] = [0.6, 1.4]
    contrast: bool = True
    contrast_range: list[float] = [0.6, 1.4]
    saturation: bool = True
    saturation_range: list[float] = [0.5, 1.5]
    blur: bool = False
    blur_radius: float = 1.5
    noise: bool = False
    noise_std: int = 15
    rotation: bool = False
    rotation_degrees: float = 15.0
    copies_per_image: int = 2
    only_annotated: bool = True
    output_original: bool = True


class AugmentFolderRequest(BaseModel):
    folder: str
    flip_horizontal: bool = True
    flip_vertical: bool = False
    brightness: bool = True
    brightness_range: list[float] = [0.6, 1.4]
    contrast: bool = True
    contrast_range: list[float] = [0.6, 1.4]
    saturation: bool = True
    saturation_range: list[float] = [0.5, 1.5]
    blur: bool = False
    blur_radius: float = 1.5
    noise: bool = False
    noise_std: int = 15
    rotation: bool = False
    rotation_degrees: float = 15.0
    copies_per_image: int = 2
    only_annotated: bool = True
    output_original: bool = True


def _build_aug_config(req) -> AugConfig:
    return AugConfig(
        flip_horizontal=req.flip_horizontal,
        flip_vertical=req.flip_vertical,
        brightness=req.brightness,
        brightness_range=tuple(req.brightness_range),
        contrast=req.contrast,
        contrast_range=tuple(req.contrast_range),
        saturation=req.saturation,
        saturation_range=tuple(req.saturation_range),
        blur=req.blur,
        blur_radius=req.blur_radius,
        noise=req.noise,
        noise_std=req.noise_std,
        rotation=req.rotation,
        rotation_degrees=req.rotation_degrees,
        copies_per_image=req.copies_per_image,
        only_annotated=req.only_annotated,
        output_original=req.output_original,
    )


@router.post("/augment/project")
def augment_project_endpoint(req: AugmentProjectRequest, background_tasks: BackgroundTasks,
                             _token: str = Depends(require_token)):
    p = _get_project(req.project_path)
    cfg = _build_aug_config(req)
    job_id = _new_job()

    def _run():
        try:
            stats = run_augmentation(p, req.output_dir, cfg)
            _job_done(job_id, stats)
        except Exception as e:
            _job_failed(job_id, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job_id}


@router.post("/augment/folder")
def augment_folder_endpoint(req: AugmentFolderRequest, background_tasks: BackgroundTasks,
                            _token: str = Depends(require_token)):
    if not os.path.isdir(req.folder):
        raise HTTPException(status_code=400, detail="Folder not found.")

    cfg = _build_aug_config(req)
    job_id = _new_job()

    def _run():
        try:
            stats = augment_from_folder(req.folder, cfg)
            _job_done(job_id, stats)
        except Exception as e:
            _job_failed(job_id, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job_id}


# ── YOLO Training ─────────────────────────────────────────────────────────────

class TrainRequest(BaseModel):
    data_yaml: str          # path to data.yaml
    model: str = "yolo11n.pt"  # base model or .pt weights file
    epochs: int = 100
    batch: int = 16
    imgsz: int = 640
    patience: int = 50
    output_dir: str = ""    # project/name for ultralytics output
    device: str = ""        # "cpu", "cuda", "mps", or "" for auto


@router.post("/train")
def train_endpoint(req: TrainRequest, background_tasks: BackgroundTasks,
                   _token: str = Depends(require_token)):
    if not os.path.isfile(req.data_yaml):
        raise HTTPException(status_code=400, detail="data_yaml file not found.")

    job_id = _new_job()

    def _run():
        try:
            from app.detection_service import _best_device
            from ultralytics import YOLO

            device = req.device or _best_device()
            model = YOLO(req.model)

            train_kwargs = dict(
                data=req.data_yaml,
                epochs=req.epochs,
                batch=req.batch,
                imgsz=req.imgsz,
                patience=req.patience,
                device=device,
                verbose=False,
            )
            if req.output_dir:
                train_kwargs["project"] = req.output_dir

            results = model.train(**train_kwargs)

            best_model = str(results.best) if hasattr(results, "best") else ""
            _job_done(job_id, {
                "best_model": best_model,
                "device": device,
            })
        except Exception as e:
            _job_failed(job_id, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job_id}
