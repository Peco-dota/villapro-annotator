"""Dataset operations — export, augmentation, split, batch export, training."""
import datetime
import json
import os
import queue
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import require_user
from app.augmentation import AugConfig, run_augmentation, augment_from_folder
from app.utils import export_yolo, export_coco, batch_export_yolo, split_dataset
from app.routers.projects import _get_project

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# Simple job tracker for long-running operations
_jobs: dict[str, dict] = {}  # job_id -> {status, result, error, epoch, total_epochs}

# Training log queues: job_id -> queue of log lines (None = sentinel/done)
_train_logs: dict[str, queue.Queue] = {}

# Cancel flags: job_id -> threading.Event (set = cancel requested)
_train_cancel: dict[str, threading.Event] = {}

# Training threads: job_id -> thread (so we can force-kill)
_train_threads: dict[str, threading.Thread] = {}

# Active training job (persisted so clients can reconnect after refresh)
_active_train_job: dict = {}  # {job_id, run_name, epochs, started_at} or {}

# Active augmentation / merge jobs (persisted so clients can reconnect after navigation)
_active_aug_job: dict = {}
_active_merge_job: dict = {}

# Cancel events for cancellable jobs (augment, batch export)
_job_cancel: dict[str, threading.Event] = {}


def _raise_in_thread(tid: int, exc_type: type) -> bool:
    """Raise an exception in a thread by its OS id. Returns True on success."""
    import ctypes
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(tid),
        ctypes.py_object(exc_type),
    )
    return res == 1


def _new_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None,
                     "epoch": 0, "total_epochs": 0, "progress": 0, "total": 0}
    return job_id


def _job_done(job_id: str, result: dict):
    _jobs[job_id] = {"status": "done", "result": result, "error": None}


def _job_failed(job_id: str, error: str):
    _jobs[job_id] = {"status": "failed", "result": None, "error": error}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _user: dict = Depends(require_user)):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job_id": job_id, **job}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, _user: dict = Depends(require_user)):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    if _jobs[job_id].get("status") != "running":
        raise HTTPException(status_code=409, detail="Job is not running.")
    event = _job_cancel.get(job_id)
    if event:
        event.set()
    return {"cancelled": job_id}


@router.get("/augment/active")
def get_active_aug(_user: dict = Depends(require_user)):
    if not _active_aug_job:
        return {"active": False}
    job_id = _active_aug_job.get("job_id")
    job = _jobs.get(job_id, {})
    return {"active": True, **_active_aug_job, **job}


@router.get("/merge/active")
def get_active_merge(_user: dict = Depends(require_user)):
    if not _active_merge_job:
        return {"active": False}
    job_id = _active_merge_job.get("job_id")
    job = _jobs.get(job_id, {})
    return {"active": True, **_active_merge_job, **job}


# ── YOLO Export ───────────────────────────────────────────────────────────────

class ExportYoloRequest(BaseModel):
    project_path: str
    output_dir: str
    split: Optional[dict] = None   # e.g. {"train": 0.8, "val": 0.1, "test": 0.1}
    generate_yaml: bool = True


@router.post("/export/yolo")
def export_yolo_endpoint(req: ExportYoloRequest, background_tasks: BackgroundTasks,
                         _user: dict = Depends(require_user)):
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
                         _user: dict = Depends(require_user)):
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
    sources: list[str]            # .annotatex project files OR YOLO dataset directories
    output_dir: str
    split: Optional[dict] = None
    generate_yaml: bool = True
    augmentation: Optional[dict] = None


@router.post("/export/batch")
def batch_export_endpoint(req: BatchExportRequest, background_tasks: BackgroundTasks,
                          _user: dict = Depends(require_user)):
    for src in req.sources:
        if not os.path.exists(src):
            raise HTTPException(status_code=400, detail=f"Source not found: {src}")

    aug_cfg = None
    if req.augmentation:
        aug_cfg = AugConfig(**req.augmentation)

    job_id = _new_job()
    cancel_event = threading.Event()
    _job_cancel[job_id] = cancel_event

    _active_merge_job.clear()
    _active_merge_job.update({
        "job_id": job_id,
        "sources": req.sources,
        "output_dir": req.output_dir,
        "started_at": datetime.datetime.now().isoformat(),
    })

    def _run():
        def progress_cb(done: int, total: int):
            _jobs[job_id]["progress"] = done
            _jobs[job_id]["total"] = total
        try:
            stats = batch_export_yolo(
                req.sources, req.output_dir,
                req.split, req.generate_yaml, aug_cfg,
                progress_cb=progress_cb, cancel_event=cancel_event,
            )
            _job_done(job_id, stats)
        except InterruptedError:
            _job_failed(job_id, "Cancelled")
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
                           _user: dict = Depends(require_user)):
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
                             _user: dict = Depends(require_user)):
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
                            _user: dict = Depends(require_user)):
    if not os.path.isdir(req.folder):
        raise HTTPException(status_code=400, detail="Folder not found.")

    cfg = _build_aug_config(req)
    job_id = _new_job()
    cancel_event = threading.Event()
    _job_cancel[job_id] = cancel_event

    _active_aug_job.clear()
    _active_aug_job.update({
        "job_id": job_id,
        "folder": req.folder,
        "started_at": datetime.datetime.now().isoformat(),
    })

    def _run():
        def progress_cb(done: int, total: int):
            _jobs[job_id]["progress"] = done
            _jobs[job_id]["total"] = total
        try:
            stats = augment_from_folder(req.folder, cfg, progress_cb=progress_cb,
                                        cancel_event=cancel_event)
            _job_done(job_id, stats)
        except InterruptedError:
            _job_failed(job_id, "Cancelled")
        except Exception as e:
            _job_failed(job_id, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job_id}


# ── YOLO Training ─────────────────────────────────────────────────────────────

MODELS_ROOT = Path(os.environ.get("VISIONQ_MODELS_DIR", "/villapro-data/models"))

_HISTORY_PATH = Path(
    os.environ.get("VISIONQ_DATA", str(Path.home()))
) / "config" / "train_history.json"


def _load_history() -> list[dict]:
    try:
        if _HISTORY_PATH.exists():
            return json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_history_entry(entry: dict) -> None:
    try:
        history = _load_history()
        history = [e for e in history if e.get("job_id") != entry["job_id"]]
        history.insert(0, entry)
        _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception:
        pass


class TrainRequest(BaseModel):
    data_yaml: str
    model: str = "yolo26n.pt"   # pretrained base model name or path to custom .pt
    epochs: int = 50
    batch: int = 8
    imgsz: int = 640
    patience: int = 15
    run_name: str = "my_training"
    device: str = ""             # "cpu", "cuda", "mps", or "" for auto


@router.get("/train/active")
def get_active_train(_user: dict = Depends(require_user)):
    """Return the currently running training job, if any."""
    if not _active_train_job:
        return {"active": False}
    job_id = _active_train_job.get("job_id")
    job = _jobs.get(job_id, {})
    return {"active": True, **_active_train_job, **job}


@router.post("/train/cancel")
def cancel_train(force: bool = False, _user: dict = Depends(require_user)):
    """Cancel the active training job.

    force=false (default): set stop flag — training stops after the current epoch.
    force=true: inject KeyboardInterrupt into the training thread immediately.
    """
    if not _active_train_job:
        raise HTTPException(status_code=404, detail="No active training job.")
    job_id = _active_train_job.get("job_id")

    cancel_event = _train_cancel.get(job_id)
    if cancel_event:
        cancel_event.set()

    if force:
        thread = _train_threads.get(job_id)
        if thread and thread.is_alive():
            _raise_in_thread(thread.ident, KeyboardInterrupt)

    return {"cancelled": job_id, "force": force}


@router.post("/train")
def train_endpoint(req: TrainRequest, background_tasks: BackgroundTasks,
                   _user: dict = Depends(require_user)):
    if not os.path.isfile(req.data_yaml):
        raise HTTPException(status_code=400, detail="data_yaml file not found.")

    # Only one training job at a time
    if _active_train_job and _jobs.get(_active_train_job.get("job_id", ""), {}).get("status") == "running":
        raise HTTPException(status_code=409, detail="A training job is already running. Cancel it first.")

    run_name = req.run_name.strip() or "my_training"
    output_dir = MODELS_ROOT / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    job_id = _new_job()
    _jobs[job_id]["total_epochs"] = req.epochs
    log_q: queue.Queue = queue.Queue()
    _train_logs[job_id] = log_q
    cancel_event = threading.Event()
    _train_cancel[job_id] = cancel_event

    _active_train_job.clear()
    _active_train_job.update({
        "job_id": job_id,
        "run_name": run_name,
        "total_epochs": req.epochs,
        "model": req.model,
        "data_yaml": req.data_yaml,
        "started_at": datetime.datetime.now().isoformat(),
    })

    def _log(msg: str):
        log_q.put(msg)

    def _run():
        try:
            from app.detection_service import _best_device
            from ultralytics import YOLO

            device = req.device or _best_device()
            _log(f"Model  : {req.model}")
            _log(f"Dataset: {req.data_yaml}")
            _log(f"Config : {req.epochs} epochs  batch={req.batch}  imgsz={req.imgsz}  patience={req.patience}")
            _log(f"Device : {device}")
            _log(f"Output : {output_dir}")
            _log("─" * 52)

            model = YOLO(req.model)
            total_epochs = req.epochs

            def on_epoch_end(trainer):
                ep = trainer.epoch + 1
                _jobs[job_id]["epoch"] = ep
                m = trainer.metrics or {}
                try:
                    bl = trainer.loss_items[0].item()
                    cl = trainer.loss_items[1].item() if len(trainer.loss_items) > 1 else 0
                    dfl = trainer.loss_items[2].item() if len(trainer.loss_items) > 2 else 0
                except Exception:
                    bl = cl = dfl = 0
                precision = m.get("metrics/precision(B)", 0)
                recall    = m.get("metrics/recall(B)", 0)
                map50     = m.get("metrics/mAP50(B)", 0)
                map5095   = m.get("metrics/mAP50-95(B)", 0)
                _log(
                    f"[{ep:>3}/{total_epochs}]  "
                    f"loss: box={bl:.3f} cls={cl:.3f} dfl={dfl:.3f}  |  "
                    f"P={precision:.3f}  R={recall:.3f}  "
                    f"mAP50={map50:.3f}  mAP50-95={map5095:.3f}"
                )
                _jobs[job_id]["last_metrics"] = {
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "mAP50": round(map50, 4),
                    "mAP50-95": round(map5095, 4),
                }
                # Check cancel flag
                if cancel_event.is_set():
                    trainer.stop = True

            model.add_callback("on_train_epoch_end", on_epoch_end)

            results = model.train(
                data=req.data_yaml,
                epochs=req.epochs,
                batch=req.batch,
                imgsz=req.imgsz,
                patience=req.patience,
                device=device,
                project=str(MODELS_ROOT),
                name=run_name,
                exist_ok=True,
                verbose=False,
            )

            finished_at = datetime.datetime.now().isoformat()

            if cancel_event.is_set():
                _log("─" * 52)
                _log("Training cancelled by user.")
                _job_failed(job_id, "Cancelled by user.")
                _save_history_entry({
                    "job_id": job_id, "run_name": run_name, "model": req.model,
                    "data_yaml": req.data_yaml, "epochs_requested": req.epochs,
                    "epochs_completed": _jobs[job_id].get("epoch", 0),
                    "status": "cancelled", "started_at": _active_train_job.get("started_at"),
                    "finished_at": finished_at, "output_dir": str(output_dir),
                    "best_model": "", "device": device,
                    "metrics": _jobs[job_id].get("last_metrics"),
                })
                _active_train_job.clear()
                return

            best = output_dir / "weights" / "best.pt"
            if not best.exists():
                for pt in output_dir.rglob("best.pt"):
                    best = pt
                    break

            _log("─" * 52)
            _log(f"Complete!  Best weights → {best}")

            best_str = str(best) if best.exists() else ""
            _job_done(job_id, {
                "best_model": best_str,
                "run_name": run_name,
                "output_dir": str(output_dir),
                "device": device,
            })
            _save_history_entry({
                "job_id": job_id, "run_name": run_name, "model": req.model,
                "data_yaml": req.data_yaml, "epochs_requested": req.epochs,
                "epochs_completed": _jobs[job_id].get("epoch", req.epochs),
                "status": "done", "started_at": _active_train_job.get("started_at"),
                "finished_at": finished_at, "output_dir": str(output_dir),
                "best_model": best_str, "device": device,
                "metrics": _jobs[job_id].get("last_metrics"),
            })
            _active_train_job.clear()
        except KeyboardInterrupt:
            _log("─" * 52)
            _log("Training force-stopped.")
            _job_failed(job_id, "Force-stopped by user.")
            _save_history_entry({
                "job_id": job_id, "run_name": run_name, "model": req.model,
                "data_yaml": req.data_yaml, "epochs_requested": req.epochs,
                "epochs_completed": _jobs[job_id].get("epoch", 0),
                "status": "cancelled", "started_at": _active_train_job.get("started_at"),
                "finished_at": datetime.datetime.now().isoformat(),
                "output_dir": str(output_dir), "best_model": "", "device": "",
                "metrics": _jobs[job_id].get("last_metrics"),
            })
            _active_train_job.clear()
        except Exception as e:
            import traceback
            _log(f"ERROR: {e}")
            _log(traceback.format_exc())
            _job_failed(job_id, str(e))
            _save_history_entry({
                "job_id": job_id, "run_name": run_name, "model": req.model,
                "data_yaml": req.data_yaml, "epochs_requested": req.epochs,
                "epochs_completed": _jobs[job_id].get("epoch", 0),
                "status": "failed", "started_at": _active_train_job.get("started_at"),
                "finished_at": datetime.datetime.now().isoformat(),
                "output_dir": str(output_dir), "best_model": "", "device": "",
                "metrics": _jobs[job_id].get("last_metrics"),
            })
            _active_train_job.clear()
        finally:
            log_q.put(None)  # sentinel

    t = threading.Thread(target=_run, daemon=True)
    _train_threads[job_id] = t
    t.start()
    return {"job_id": job_id, "output_dir": str(output_dir)}


@router.get("/train/log/{job_id}")
def train_log_stream(job_id: str, request: Request, _user: dict = Depends(require_user)):
    """SSE stream of training log lines for a given job."""
    log_q = _train_logs.get(job_id)
    if log_q is None:
        raise HTTPException(status_code=404, detail="No log stream for this job.")

    async def _generate():
        import asyncio
        loop = asyncio.get_event_loop()
        while True:
            if await request.is_disconnected():
                break
            try:
                line = await loop.run_in_executor(None, lambda: log_q.get(timeout=1))
                if line is None:
                    yield "event: done\ndata: \n\n"
                    break
                yield f"data: {line}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ── Training history ──────────────────────────────────────────────────────────

@router.get("/train/history")
def get_train_history(_user: dict = Depends(require_user)):
    """Return all past training runs, newest first."""
    return _load_history()


@router.delete("/train/history/{job_id}")
def delete_train_history_entry(job_id: str, _user: dict = Depends(require_user)):
    """Remove a single entry from training history."""
    history = _load_history()
    updated = [e for e in history if e.get("job_id") != job_id]
    if len(updated) == len(history):
        raise HTTPException(status_code=404, detail="Entry not found.")
    try:
        _HISTORY_PATH.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"deleted": job_id}
