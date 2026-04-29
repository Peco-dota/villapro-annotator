"""Utility functions for VisionQ server (PyQt-free)."""
import colorsys
import os
import json
import random
import shutil
from pathlib import Path
from typing import Optional

# ── Color generation ─────────────────────────────────────────────────────────

_BASE_COLORS = [
    "#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#a855f7",
    "#06b6d4", "#f97316", "#ec4899", "#14b8a6", "#84cc16",
    "#6366f1", "#f43f5e", "#8b5cf6", "#0ea5e9", "#10b981", "#eab308",
]


def generate_class_colors(n: int) -> list[str]:
    colors = []
    for i in range(n):
        if i < len(_BASE_COLORS):
            colors.append(_BASE_COLORS[i])
        else:
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
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r, g, b, alpha


# ── YOLO Export ──────────────────────────────────────────────────────────────

def export_yolo(project, output_dir: str, split: Optional[dict] = None,
                generate_yaml: bool = True) -> dict:
    output_dir = Path(output_dir)

    if split:
        splits = list(split.keys())
        ratios = list(split.values())
    else:
        splits = ["images"]
        ratios = [1.0]

    all_images = list(project.images)

    if split:
        random.seed(42)
        random.shuffle(all_images)

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
                label_path.touch()

    classes_txt = output_dir / "classes.txt"
    with open(classes_txt, "w") as f:
        for c in project.classes:
            f.write(c.name + "\n")

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
        coco["images"].append({"id": img_id, "file_name": fn, "width": w, "height": h})

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
    from app.project import Project
    from app.annotation import BoundingBox
    import copy

    output_dir = Path(output_dir)

    projects: list[Project] = []
    for p in project_paths:
        proj = Project.load(p)
        projects.append(proj)

    unified_names: list[str] = []
    name_to_uid: dict[str, int] = {}
    for proj in projects:
        for cls in proj.classes:
            if cls.name not in name_to_uid:
                name_to_uid[cls.name] = len(unified_names)
                unified_names.append(cls.name)

    all_entries: list[tuple] = []

    for pidx, proj in enumerate(projects):
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

    from PIL import Image as PILImage

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

    with open(output_dir / "classes.txt", "w") as f:
        for name in unified_names:
            f.write(name + "\n")

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

    for d in (img_dir, lbl_dir):
        try:
            d.rmdir()
        except OSError:
            pass

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

RECENT_PROJECTS_FILE = Path(os.environ.get("VISIONQ_DATA", str(Path.home()))) / "config" / "recent_projects.json"


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
