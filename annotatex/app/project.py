"""Project data model and serialization for AnnotateX."""
import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from app.annotation import BoundingBox, ClassDef
from app.utils import generate_class_colors

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


@dataclass
class ImageAnnotation:
    """Annotations for a single image."""
    filename: str
    boxes: list = field(default_factory=list)  # list[BoundingBox]

    @property
    def box_count(self) -> int:
        return len(self.boxes)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "boxes": [b.to_dict() for b in self.boxes],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ImageAnnotation":
        ia = cls(filename=d["filename"])
        ia.boxes = [BoundingBox.from_dict(b) for b in d.get("boxes", [])]
        return ia


class Project:
    """Holds all project state."""

    def __init__(self):
        self.path: Optional[str] = None           # .annotatex file path
        self.name: str = "Untitled Project"
        self.image_folder: str = ""
        self.images: list[str] = []               # sorted list of image filenames
        self.classes: list[ClassDef] = []
        self.annotations: dict[str, ImageAnnotation] = {}  # filename -> ImageAnnotation
        self.current_index: int = 0
        self.modified: bool = False
        self._annotated_count_cache: Optional[int] = None

        # Settings
        self.settings: dict = {
            "auto_save_interval": 5,
            "canvas_bg": "#2a2a2a",
            "crosshair": False,
            "annotation_opacity": 0.15,
            "zoom_to_fit_on_load": True,
        }

    # ── Image management ─────────────────────────────────────────────────────

    def scan_images(self) -> int:
        """Scan image_folder and populate self.images. Returns count."""
        if not self.image_folder or not os.path.isdir(self.image_folder):
            return 0
        found = []
        for f in sorted(os.listdir(self.image_folder)):
            if Path(f).suffix.lower() in IMAGE_EXTENSIONS:
                found.append(f)
        self.images = found
        # Ensure annotation entries exist for all
        for fn in self.images:
            if fn not in self.annotations:
                self.annotations[fn] = ImageAnnotation(filename=fn)
        return len(self.images)

    def image_path(self, filename: str) -> str:
        return os.path.join(self.image_folder, filename)

    def current_image_filename(self) -> Optional[str]:
        if not self.images:
            return None
        return self.images[self.current_index]

    def current_annotation(self) -> Optional[ImageAnnotation]:
        fn = self.current_image_filename()
        if fn is None:
            return None
        return self.annotations.setdefault(fn, ImageAnnotation(filename=fn))

    # ── Class management ─────────────────────────────────────────────────────

    def add_class(self, name: str) -> ClassDef:
        cls_id = len(self.classes)
        colors = generate_class_colors(cls_id + 1)
        c = ClassDef(id=cls_id, name=name, color=colors[cls_id])
        self.classes.append(c)
        self.modified = True
        return c

    def remove_class(self, cls_id: int) -> bool:
        """Remove class by id. Returns False if in use."""
        idx = next((i for i, c in enumerate(self.classes) if c.id == cls_id), -1)
        if idx == -1:
            return False
        self.classes.pop(idx)
        # Re-index remaining classes
        for i, c in enumerate(self.classes):
            c.id = i
        # Update all annotations
        for ia in self.annotations.values():
            ia.boxes = [b for b in ia.boxes if b.class_id != cls_id]
            for b in ia.boxes:
                if b.class_id > cls_id:
                    b.class_id -= 1
        self.modified = True
        return True

    def get_class(self, cls_id: int) -> Optional[ClassDef]:
        for c in self.classes:
            if c.id == cls_id:
                return c
        return None

    def class_annotation_count(self, cls_id: int) -> int:
        total = 0
        for ia in self.annotations.values():
            total += sum(1 for b in ia.boxes if b.class_id == cls_id)
        return total

    # ── Stats ─────────────────────────────────────────────────────────────────

    def invalidate_annotated_count(self):
        self._annotated_count_cache = None

    @property
    def annotated_count(self) -> int:
        if self._annotated_count_cache is None:
            self._annotated_count_cache = sum(
                1 for ia in self.annotations.values() if ia.box_count > 0
            )
        return self._annotated_count_cache

    @property
    def total_count(self) -> int:
        return len(self.images)

    @property
    def total_box_count(self) -> int:
        return sum(ia.box_count for ia in self.annotations.values())

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "image_folder": self.image_folder,
            "classes": [c.to_dict() for c in self.classes],
            "annotations": {fn: ia.to_dict() for fn, ia in self.annotations.items()},
            "current_index": self.current_index,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls()
        p.name = d.get("name", "Untitled Project")
        p.image_folder = d.get("image_folder", "")
        p.classes = [ClassDef.from_dict(c) for c in d.get("classes", [])]
        p.annotations = {
            fn: ImageAnnotation.from_dict(ia)
            for fn, ia in d.get("annotations", {}).items()
        }
        p.current_index = d.get("current_index", 0)
        p.settings.update(d.get("settings", {}))
        return p

    def save(self, path: Optional[str] = None) -> str:
        save_path = path or self.path
        if not save_path:
            raise ValueError("No save path specified")
        self.path = save_path
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        self.modified = False
        return save_path

    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        p = cls.from_dict(d)
        p.path = path
        p.scan_images()
        # Clamp index
        if p.images:
            p.current_index = max(0, min(p.current_index, len(p.images) - 1))
        p.modified = False
        return p

    # ── YOLO I/O ─────────────────────────────────────────────────────────────

    def load_yolo_labels(self):
        """Import existing YOLO .txt labels from image_folder."""
        for fn in self.images:
            label_path = os.path.join(
                self.image_folder,
                Path(fn).stem + ".txt"
            )
            if os.path.exists(label_path):
                boxes = []
                with open(label_path) as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) == 5:
                            try:
                                cls_id, cx, cy, w, h = int(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                                boxes.append(BoundingBox(class_id=cls_id, cx=cx, cy=cy, w=w, h=h))
                            except ValueError:
                                pass
                if boxes:
                    self.annotations.setdefault(fn, ImageAnnotation(filename=fn)).boxes = boxes
