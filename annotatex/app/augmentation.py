"""
AnnotateX — Dataset Augmentation
Applies image + bounding-box-aware transformations to multiply dataset size.
All augmentations correctly adjust normalized YOLO bounding box coordinates.
"""
from __future__ import annotations
import copy
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

if TYPE_CHECKING:
    from app.project import Project
    from app.annotation import BoundingBox


# ── Augmentation config ───────────────────────────────────────────────────────

@dataclass
class AugConfig:
    """User-selected augmentation options."""
    flip_horizontal: bool = True
    flip_vertical: bool = False

    brightness: bool = True
    brightness_range: tuple[float, float] = (0.6, 1.4)   # factor

    contrast: bool = True
    contrast_range: tuple[float, float] = (0.6, 1.4)

    saturation: bool = True
    saturation_range: tuple[float, float] = (0.5, 1.5)

    blur: bool = False
    blur_radius: float = 1.5

    noise: bool = False
    noise_std: int = 15                                   # 0-255 std

    rotation: bool = False
    rotation_degrees: float = 15.0                       # ±degrees

    copies_per_image: int = 2                            # augmented versions per image
    only_annotated: bool = True                          # skip unannotated images
    output_original: bool = True                         # include originals in output


# ── Box transform helpers ─────────────────────────────────────────────────────

def _flip_box_h(box: "BoundingBox") -> "BoundingBox":
    """Mirror bounding box horizontally (cx flips, cy unchanged)."""
    b = copy.deepcopy(box)
    b.cx = 1.0 - box.cx
    return b


def _flip_box_v(box: "BoundingBox") -> "BoundingBox":
    """Mirror bounding box vertically."""
    b = copy.deepcopy(box)
    b.cy = 1.0 - box.cy
    return b


def _rotate_box(box: "BoundingBox", degrees: float,
                img_w: int, img_h: int) -> Optional["BoundingBox"]:
    """
    Rotate a bounding box around the image center.
    Returns a new axis-aligned bounding box that contains the rotated corners.
    Returns None if the resulting box is entirely outside the image.
    """
    import math
    rad = math.radians(degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    # Convert to pixel coords
    cx_px = box.cx * img_w
    cy_px = box.cy * img_h
    w_px = box.w * img_w
    h_px = box.h * img_h

    # Four corners relative to image center
    icx, icy = img_w / 2, img_h / 2
    corners = [
        (cx_px - w_px / 2 - icx, cy_px - h_px / 2 - icy),
        (cx_px + w_px / 2 - icx, cy_px - h_px / 2 - icy),
        (cx_px + w_px / 2 - icx, cy_px + h_px / 2 - icy),
        (cx_px - w_px / 2 - icx, cy_px + h_px / 2 - icy),
    ]
    rotated = [(x * cos_a - y * sin_a + icx,
                x * sin_a + y * cos_a + icy) for x, y in corners]

    xs = [p[0] for p in rotated]
    ys = [p[1] for p in rotated]
    x1, x2 = max(0, min(xs)), min(img_w, max(xs))
    y1, y2 = max(0, min(ys)), min(img_h, max(ys))

    if x2 - x1 < 2 or y2 - y1 < 2:
        return None

    b = copy.deepcopy(box)
    b.cx = ((x1 + x2) / 2) / img_w
    b.cy = ((y1 + y2) / 2) / img_h
    b.w = (x2 - x1) / img_w
    b.h = (y2 - y1) / img_h
    return b


# ── Per-image augmentation ────────────────────────────────────────────────────

def _apply_single(img: Image.Image, boxes: list["BoundingBox"],
                  cfg: AugConfig, rng: random.Random) -> list[tuple[Image.Image, list["BoundingBox"]]]:
    """
    Generate `copies_per_image` augmented versions of one image.
    Returns list of (augmented_image, augmented_boxes).
    """
    results = []
    img_w, img_h = img.size

    for _ in range(cfg.copies_per_image):
        aug_img = img.copy()
        aug_boxes = copy.deepcopy(boxes)

        # ── Flip horizontal ───────────────────────────────────────────────────
        if cfg.flip_horizontal and rng.random() < 0.5:
            aug_img = aug_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            aug_boxes = [_flip_box_h(b) for b in aug_boxes]

        # ── Flip vertical ─────────────────────────────────────────────────────
        if cfg.flip_vertical and rng.random() < 0.5:
            aug_img = aug_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            aug_boxes = [_flip_box_v(b) for b in aug_boxes]

        # ── Rotation ──────────────────────────────────────────────────────────
        if cfg.rotation and rng.random() < 0.7:
            deg = rng.uniform(-cfg.rotation_degrees, cfg.rotation_degrees)
            aug_img = aug_img.rotate(deg, expand=False, fillcolor=(114, 114, 114))
            new_boxes = []
            for b in aug_boxes:
                rb = _rotate_box(b, -deg, img_w, img_h)  # PIL rotates CCW
                if rb is not None:
                    new_boxes.append(rb)
            aug_boxes = new_boxes

        # ── Brightness ────────────────────────────────────────────────────────
        if cfg.brightness and rng.random() < 0.7:
            factor = rng.uniform(*cfg.brightness_range)
            aug_img = ImageEnhance.Brightness(aug_img).enhance(factor)

        # ── Contrast ──────────────────────────────────────────────────────────
        if cfg.contrast and rng.random() < 0.7:
            factor = rng.uniform(*cfg.contrast_range)
            aug_img = ImageEnhance.Contrast(aug_img).enhance(factor)

        # ── Saturation ────────────────────────────────────────────────────────
        if cfg.saturation and rng.random() < 0.7:
            factor = rng.uniform(*cfg.saturation_range)
            aug_img = ImageEnhance.Color(aug_img).enhance(factor)

        # ── Blur ──────────────────────────────────────────────────────────────
        if cfg.blur and rng.random() < 0.4:
            aug_img = aug_img.filter(ImageFilter.GaussianBlur(radius=cfg.blur_radius))

        # ── Noise ─────────────────────────────────────────────────────────────
        if cfg.noise and rng.random() < 0.4:
            arr = np.array(aug_img, dtype=np.int16)
            noise = np.random.normal(0, cfg.noise_std, arr.shape).astype(np.int16)
            arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
            aug_img = Image.fromarray(arr)

        results.append((aug_img, aug_boxes))

    return results


# ── Main augmentation runner ──────────────────────────────────────────────────

def run_augmentation(project: "Project", output_dir: str,
                     cfg: AugConfig,
                     progress_cb=None) -> dict:
    """
    Augment the dataset and write to output_dir.
    progress_cb(current, total) called for progress updates.
    Returns stats dict.
    """
    from app.annotation import BoundingBox
    output_dir = Path(output_dir)
    img_out = output_dir / "images"
    lbl_out = output_dir / "labels"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    rng = random.Random(42)
    stats = {"original": 0, "augmented": 0, "skipped": 0}
    total = len(project.images)

    for i, fn in enumerate(project.images):
        if progress_cb:
            progress_cb(i, total)

        ia = project.annotations.get(fn)
        has_boxes = ia is not None and len(ia.boxes) > 0

        if cfg.only_annotated and not has_boxes:
            stats["skipped"] += 1
            continue

        src_path = project.image_path(fn)
        if not os.path.exists(src_path):
            stats["skipped"] += 1
            continue

        try:
            img = Image.open(src_path).convert("RGB")
        except Exception:
            stats["skipped"] += 1
            continue

        stem = Path(fn).stem
        suffix = Path(fn).suffix.lower() or ".jpg"
        boxes = ia.boxes if ia else []

        # ── Original ──────────────────────────────────────────────────────────
        if cfg.output_original:
            img.save(img_out / fn)
            _write_label(lbl_out / (stem + ".txt"), boxes)
            stats["original"] += 1

        # ── Augmented copies ──────────────────────────────────────────────────
        variants = _apply_single(img, boxes, cfg, rng)
        for j, (aug_img, aug_boxes) in enumerate(variants):
            aug_fn = f"{stem}_aug{j + 1}{suffix}"
            aug_img.save(img_out / aug_fn, quality=95)
            _write_label(lbl_out / f"{stem}_aug{j + 1}.txt", aug_boxes)
            stats["augmented"] += 1

    if progress_cb:
        progress_cb(total, total)

    # Write classes.txt
    with open(output_dir / "classes.txt", "w") as f:
        for c in project.classes:
            f.write(c.name + "\n")

    return stats


def _write_label(path: Path, boxes: list["BoundingBox"]):
    with open(path, "w") as f:
        for b in boxes:
            f.write(b.to_yolo_line() + "\n")


# ── Folder-based augmentation (post-export in-place) ─────────────────────────

def augment_from_folder(folder: str, cfg: AugConfig, progress_cb=None) -> dict:
    """
    Augment all images in <folder>/images/ using paired labels from <folder>/labels/.
    Augmented copies are written back into the same images/ and labels/ directories
    alongside the originals. Files whose stem already contains '_aug' are skipped so
    re-running this function on the same folder is safe.

    Returns stats dict: {"original": N, "augmented": N, "skipped": N}
    """
    from app.annotation import BoundingBox

    folder = Path(folder)
    img_dir = folder / "images"
    lbl_dir = folder / "labels"

    if not img_dir.exists():
        raise FileNotFoundError(f"No 'images' subfolder found in {folder}")
    lbl_dir.mkdir(exist_ok=True)

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    # Only process originals — skip files that are already augmented copies.
    image_files = sorted(
        p for p in img_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTS and "_aug" not in p.stem
    )

    stats = {"original": len(image_files), "augmented": 0, "skipped": 0}
    rng = random.Random(42)
    total = len(image_files)

    for i, img_path in enumerate(image_files):
        if progress_cb:
            progress_cb(i, total)

        # Parse the paired YOLO label file
        lbl_path = lbl_dir / (img_path.stem + ".txt")
        boxes: list[BoundingBox] = []
        if lbl_path.exists():
            with open(lbl_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 5:
                        try:
                            boxes.append(BoundingBox(
                                class_id=int(parts[0]),
                                cx=float(parts[1]),
                                cy=float(parts[2]),
                                w=float(parts[3]),
                                h=float(parts[4]),
                            ))
                        except ValueError:
                            pass

        if cfg.only_annotated and not boxes:
            stats["skipped"] += 1
            continue

        try:
            img = Image.open(img_path).convert("RGB")
        except Exception:
            stats["skipped"] += 1
            continue

        suffix = img_path.suffix.lower()
        variants = _apply_single(img, boxes, cfg, rng)
        for j, (aug_img, aug_boxes) in enumerate(variants):
            aug_stem = f"{img_path.stem}_aug{j + 1}"
            aug_img.save(img_dir / (aug_stem + suffix), quality=95)
            _write_label(lbl_dir / (aug_stem + ".txt"), aug_boxes)
            stats["augmented"] += 1

    if progress_cb:
        progress_cb(total, total)

    return stats
