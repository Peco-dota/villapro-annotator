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
