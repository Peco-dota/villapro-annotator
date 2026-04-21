"""Utility functions for AnnotateX."""
import colorsys
import os
import json
import random
import shutil
from pathlib import Path
from typing import Optional

# ── Color generation ─────────────────────────────────────────────────────────

# Visually distinct base palette
_BASE_COLORS = [
    "#ef4444",  # red
    "#3b82f6",  # blue
    "#22c55e",  # green
    "#f59e0b",  # amber
    "#a855f7",  # purple
    "#06b6d4",  # cyan
    "#f97316",  # orange
    "#ec4899",  # pink
    "#14b8a6",  # teal
    "#84cc16",  # lime
    "#6366f1",  # indigo
    "#f43f5e",  # rose
    "#8b5cf6",  # violet
    "#0ea5e9",  # sky
    "#10b981",  # emerald
    "#eab308",  # yellow
]


def generate_class_colors(n: int) -> list[str]:
    """Return a list of n distinct hex color strings."""
    colors = []
    for i in range(n):
        if i < len(_BASE_COLORS):
            colors.append(_BASE_COLORS[i])
        else:
            # Generate via HSV rotation for overflow
            hue = (i * 0.618033988749895) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
            colors.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
    return colors


def class_color(cls_id: int) -> str:
    if cls_id < len(_BASE_COLORS):
        return _BASE_COLORS[cls_id]
    hue = (cls_id * 0.618033988749895) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """Convert #rrggbb to (r, g, b, a)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r, g, b, alpha


# ── YOLO Export ──────────────────────────────────────────────────────────────

def export_yolo(project, output_dir: str, split: Optional[dict] = None,
                generate_yaml: bool = True) -> dict:
    """
    Export annotations in YOLO format.

    split: {"train": 0.8, "val": 0.1, "test": 0.1} or None (no split)
    Returns summary dict.
    """
    output_dir = Path(output_dir)

    if split:
        splits = list(split.keys())
        ratios = list(split.values())
    else:
        splits = ["images"]
        ratios = [1.0]

    # Build image list
    images_with_annotations = [
        fn for fn in project.images
        if fn in project.annotations
    ]
    all_images = list(project.images)

    # Shuffle for split
    if split:
        random.seed(42)
        random.shuffle(all_images)

    # Partition
    partitions: dict[str, list[str]] = {}
    idx = 0
    for i, sp in enumerate(splits):
        if i == len(splits) - 1:
            partitions[sp] = all_images[idx:]
        else:
            count = int(len(all_images) * ratios[i])
            partitions[sp] = all_images[idx:idx + count]
            idx += count

    stats = {"images": 0, "annotations": 0, "classes": len(project.classes)}

    for sp, files in partitions.items():
        if split:
            img_out = output_dir / sp / "images"
            lbl_out = output_dir / sp / "labels"
        else:
            img_out = output_dir / "images"
            lbl_out = output_dir / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for fn in files:
            src = os.path.join(project.image_folder, fn)
            if os.path.exists(src):
                shutil.copy2(src, img_out / fn)
                stats["images"] += 1

            ia = project.annotations.get(fn)
            label_path = lbl_out / (Path(fn).stem + ".txt")
            if ia and ia.boxes:
                with open(label_path, "w") as f:
                    for box in ia.boxes:
                        f.write(box.to_yolo_line() + "\n")
                stats["annotations"] += len(ia.boxes)
            else:
                # Write empty label file
                label_path.touch()

    # classes.txt
    classes_txt = output_dir / "classes.txt"
    with open(classes_txt, "w") as f:
        for c in project.classes:
            f.write(c.name + "\n")

    # data.yaml
    if generate_yaml and split:
        yaml_path = output_dir / "data.yaml"
        with open(yaml_path, "w") as f:
            f.write(f"path: {output_dir.resolve()}\n")
            for sp in splits:
                f.write(f"{sp}: {sp}/images\n")
            f.write(f"\nnc: {len(project.classes)}\n")
            names = [c.name for c in project.classes]
            f.write(f"names: {names}\n")

    return stats


# ── COCO Export ──────────────────────────────────────────────────────────────

def export_coco(project, output_dir: str) -> dict:
    """Export annotations in COCO JSON format."""
    from PIL import Image as PILImage

    output_dir = Path(output_dir)
    img_out = output_dir / "images"
    img_out.mkdir(parents=True, exist_ok=True)

    coco = {
        "info": {"description": project.name, "version": "1.0"},
        "licenses": [],
        "categories": [
            {"id": c.id + 1, "name": c.name, "supercategory": "object"}
            for c in project.classes
        ],
        "images": [],
        "annotations": [],
    }

    ann_id = 1
    for img_id, fn in enumerate(project.images, 1):
        src = os.path.join(project.image_folder, fn)
        if not os.path.exists(src):
            continue

        try:
            with PILImage.open(src) as img:
                w, h = img.size
        except Exception:
            continue

        shutil.copy2(src, img_out / fn)
        coco["images"].append({
            "id": img_id,
            "file_name": fn,
            "width": w,
            "height": h,
        })

        ia = project.annotations.get(fn)
        if ia:
            for box in ia.boxes:
                px, py, pw, ph = box.to_pixel_xywh(w, h)
                coco["annotations"].append({
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": box.class_id + 1,
                    "bbox": [px, py, pw, ph],
                    "area": pw * ph,
                    "iscrowd": 0,
                })
                ann_id += 1

    with open(output_dir / "annotations.json", "w") as f:
        json.dump(coco, f, indent=2)

    return {"images": len(coco["images"]), "annotations": ann_id - 1,
            "classes": len(project.classes)}


# ── Batch (multi-project) YOLO Export ────────────────────────────────────────

def batch_export_yolo(project_paths: list[str], output_dir: str,
                      split: Optional[dict] = None,
                      generate_yaml: bool = True,
                      aug_cfg=None,
                      progress_cb=None) -> dict:
    """
    Load multiple .annotatex projects, merge them with unified class IDs
    (matched by name), then export as one YOLO dataset.

    project_paths : list of .annotatex file paths
    split         : {"train": 0.8, "val": 0.1, "test": 0.1} or None
    aug_cfg       : AugConfig or None — if set, augmented copies are written
                    alongside originals
    progress_cb   : callable(current, total) for progress updates
    """
    from app.project import Project
    from app.annotation import BoundingBox, ClassDef
    import copy

    output_dir = Path(output_dir)

    # ── 1. Load all projects ──────────────────────────────────────────────────
    projects: list[Project] = []
    for p in project_paths:
        proj = Project.load(p)
        projects.append(proj)

    # ── 2. Build unified class list (by name, order of first appearance) ──────
    unified_names: list[str] = []
    name_to_uid: dict[str, int] = {}
    for proj in projects:
        for cls in proj.classes:
            if cls.name not in name_to_uid:
                name_to_uid[cls.name] = len(unified_names)
                unified_names.append(cls.name)

    # ── 3. Collect all (image_path, boxes_remapped, stem) entries ────────────
    # stem is used for the output filename; prefix with project index to avoid
    # collisions when two projects have images with the same filename.
    all_entries: list[tuple] = []  # (abs_src, remapped_boxes, stem, suffix)

    for pidx, proj in enumerate(projects):
        # Build per-project class id → unified id map
        remap: dict[int, int] = {}
        for cls in proj.classes:
            remap[cls.id] = name_to_uid[cls.name]

        for fn in proj.images:
            src = proj.image_path(fn)
            if not os.path.exists(src):
                continue
            ia = proj.annotations.get(fn)
            boxes = []
            if ia:
                for b in ia.boxes:
                    nb = copy.deepcopy(b)
                    nb.class_id = remap.get(b.class_id, b.class_id)
                    boxes.append(nb)
            stem = f"p{pidx}_{Path(fn).stem}"
            suffix = Path(fn).suffix.lower() or ".jpg"
            all_entries.append((src, boxes, stem, suffix))

    # ── 4. Split ──────────────────────────────────────────────────────────────
    if split:
        splits = list(split.keys())
        ratios = list(split.values())
        random.seed(42)
        random.shuffle(all_entries)
        partitions: dict[str, list] = {}
        idx = 0
        for i, sp in enumerate(splits):
            if i == len(splits) - 1:
                partitions[sp] = all_entries[idx:]
            else:
                count = int(len(all_entries) * ratios[i])
                partitions[sp] = all_entries[idx:idx + count]
                idx += count
    else:
        partitions = {"images": all_entries}

    # ── 5. Write files ────────────────────────────────────────────────────────
    from PIL import Image as PILImage
    import numpy as np

    stats = {"images": 0, "augmented": 0, "annotations": 0,
             "classes": len(unified_names), "projects": len(projects)}

    total_entries = len(all_entries)
    done = 0

    rng = random.Random(42)

    for sp, entries in partitions.items():
        if split:
            img_out = output_dir / sp / "images"
            lbl_out = output_dir / sp / "labels"
        else:
            img_out = output_dir / "images"
            lbl_out = output_dir / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for src, boxes, stem, suffix in entries:
            if progress_cb:
                progress_cb(done, total_entries)
            done += 1

            out_fn = stem + suffix

            # Copy / save original
            pil_img = None
            try:
                if aug_cfg is not None:
                    pil_img = PILImage.open(src).convert("RGB")
                    if aug_cfg.output_original:
                        pil_img.save(img_out / out_fn)
                        _write_label_batch(lbl_out / (stem + ".txt"), boxes)
                        stats["images"] += 1
                        stats["annotations"] += len(boxes)
                else:
                    shutil.copy2(src, img_out / out_fn)
                    _write_label_batch(lbl_out / (stem + ".txt"), boxes)
                    stats["images"] += 1
                    stats["annotations"] += len(boxes)
            except Exception:
                continue

            # Augmented copies
            if aug_cfg is not None and (not aug_cfg.only_annotated or boxes):
                try:
                    if pil_img is None:
                        pil_img = PILImage.open(src).convert("RGB")
                    from app.augmentation import _apply_single
                    variants = _apply_single(pil_img, boxes, aug_cfg, rng)
                    for j, (aug_img, aug_boxes) in enumerate(variants):
                        aug_stem = f"{stem}_aug{j + 1}"
                        aug_img.save(img_out / (aug_stem + suffix), quality=95)
                        _write_label_batch(lbl_out / (aug_stem + ".txt"), aug_boxes)
                        stats["augmented"] += 1
                        stats["annotations"] += len(aug_boxes)
                except Exception:
                    pass

    if progress_cb:
        progress_cb(total_entries, total_entries)

    # ── 6. classes.txt ────────────────────────────────────────────────────────
    with open(output_dir / "classes.txt", "w") as f:
        for name in unified_names:
            f.write(name + "\n")

    # ── 7. data.yaml ─────────────────────────────────────────────────────────
    if generate_yaml and split:
        yaml_path = output_dir / "data.yaml"
        with open(yaml_path, "w") as f:
            f.write(f"path: {output_dir.resolve()}\n")
            for sp in splits:
                f.write(f"{sp}: {sp}/images\n")
            f.write(f"\nnc: {len(unified_names)}\n")
            f.write(f"names: {unified_names}\n")

    return stats


def _write_label_batch(path: Path, boxes: list):
    with open(path, "w") as f:
        for b in boxes:
            f.write(b.to_yolo_line() + "\n")


# ── Dataset split ─────────────────────────────────────────────────────────────

def split_dataset(folder: str, split: dict, generate_yaml: bool = True) -> dict:
    """
    Partition a flat YOLO dataset folder into train / val / (optional) test subfolders.

    Expects:
        <folder>/images/   — all image files
        <folder>/labels/   — matching .txt label files
        <folder>/classes.txt — class names (used for data.yaml)

    Files are *moved* (not copied), so no extra disk space is required.
    The now-empty images/ and labels/ directories are removed afterwards.

    split: e.g. {"train": 0.8, "val": 0.1, "test": 0.1}
           Values are normalised internally, so they don't need to sum to 1.

    Returns stats dict: {"total": N, "train": n, "val": n, "test": n}
    """
    folder = Path(folder)
    img_dir = folder / "images"
    lbl_dir = folder / "labels"

    if not img_dir.exists():
        raise FileNotFoundError(f"No 'images' subfolder found in {folder}")

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    image_files = sorted(
        p.name for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS
    )
    if not image_files:
        raise ValueError("No image files found in images/ folder.")

    splits = list(split.keys())
    raw_ratios = list(split.values())
    total_ratio = sum(raw_ratios)
    ratios = [r / total_ratio for r in raw_ratios]

    random.seed(42)
    random.shuffle(image_files)

    # Partition image list
    partitions: dict[str, list[str]] = {}
    idx = 0
    for i, sp in enumerate(splits):
        if i == len(splits) - 1:
            partitions[sp] = image_files[idx:]
        else:
            count = int(len(image_files) * ratios[i])
            partitions[sp] = image_files[idx:idx + count]
            idx += count

    stats: dict[str, int] = {"total": len(image_files)}
    for sp in splits:
        stats[sp] = 0

    for sp, files in partitions.items():
        sp_img = folder / sp / "images"
        sp_lbl = folder / sp / "labels"
        sp_img.mkdir(parents=True, exist_ok=True)
        sp_lbl.mkdir(parents=True, exist_ok=True)

        for fn in files:
            src_img = img_dir / fn
            if src_img.exists():
                shutil.move(str(src_img), str(sp_img / fn))

            stem = Path(fn).stem
            src_lbl = lbl_dir / (stem + ".txt")
            if src_lbl.exists():
                shutil.move(str(src_lbl), str(sp_lbl / (stem + ".txt")))

            stats[sp] += 1

    # Remove now-empty flat directories (silently leave them if non-empty)
    for d in (img_dir, lbl_dir):
        try:
            d.rmdir()
        except OSError:
            pass

    # Read class names for data.yaml
    class_names: list[str] = []
    classes_txt = folder / "classes.txt"
    if classes_txt.exists():
        with open(classes_txt) as f:
            class_names = [line.strip() for line in f if line.strip()]

    if generate_yaml:
        yaml_path = folder / "data.yaml"
        with open(yaml_path, "w") as f:
            f.write(f"path: {folder.resolve()}\n")
            for sp in splits:
                f.write(f"{sp}: {sp}/images\n")
            f.write(f"\nnc: {len(class_names)}\n")
            f.write(f"names: {class_names}\n")

    return stats


# ── Recent projects ───────────────────────────────────────────────────────────

RECENT_PROJECTS_FILE = Path.home() / ".annotatex_recent.json"


def load_recent_projects() -> list[str]:
    if RECENT_PROJECTS_FILE.exists():
        try:
            with open(RECENT_PROJECTS_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def add_recent_project(path: str):
    recent = load_recent_projects()
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    recent = recent[:10]
    try:
        with open(RECENT_PROJECTS_FILE, "w") as f:
            json.dump(recent, f)
    except Exception:
        pass


def remove_recent_project(path: str):
    recent = load_recent_projects()
    if path in recent:
        recent.remove(path)
    try:
        with open(RECENT_PROJECTS_FILE, "w") as f:
            json.dump(recent, f)
    except Exception:
        pass


# ── Image loading ─────────────────────────────────────────────────────────────

def load_pixmap_safe(path: str):
    """Load a QPixmap safely, returning None on error."""
    from PyQt6.QtGui import QPixmap
    if not os.path.exists(path):
        return None
    pm = QPixmap(path)
    return pm if not pm.isNull() else None


def generate_thumbnail(path: str, size: int = 80):
    """Generate a QPixmap thumbnail."""
    from PyQt6.QtGui import QPixmap, QImage
    from PyQt6.QtCore import Qt
    pm = QPixmap(path)
    if pm.isNull():
        return None
    return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
