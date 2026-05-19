"""Project data model and serialization."""
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
        self.path: Optional[str] = None
        self.name: str = "Untitled Project"
        self.image_folders: list[str] = []
        self.image_folder: str = ""  # always == image_folders[0] (or "" if empty)
        self.images: list[str] = []
        self.classes: list[ClassDef] = []
        self.annotations: dict[str, ImageAnnotation] = {}
        self.current_index: int = 0
        self.modified: bool = False
        self._annotated_count_cache: Optional[int] = None

        self.settings: dict = {
            "auto_save_interval": 5,
            "canvas_bg": "#2a2a2a",
            "crosshair": False,
            "annotation_opacity": 0.15,
            "zoom_to_fit_on_load": True,
        }

    def scan_images(self) -> int:
        seen: set[str] = set()
        found: list[str] = []
        for folder in self.image_folders:
            if not folder or not os.path.isdir(folder):
                continue
            for f in sorted(os.listdir(folder)):
                if Path(f).suffix.lower() in IMAGE_EXTENSIONS:
                    full = os.path.normpath(os.path.join(folder, f))
                    if full not in seen:
                        seen.add(full)
                        found.append(full)
        self.images = found
        for fn in self.images:
            if fn not in self.annotations:
                self.annotations[fn] = ImageAnnotation(filename=fn)
        return len(self.images)

    def image_path(self, filename: str) -> str:
        if os.path.isabs(filename):
            return filename
        # backward compat: bare filename from old single-folder project
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

    def add_class(self, name: str) -> ClassDef:
        cls_id = len(self.classes)
        colors = generate_class_colors(cls_id + 1)
        c = ClassDef(id=cls_id, name=name, color=colors[cls_id])
        self.classes.append(c)
        self.modified = True
        return c

    def remove_class(self, cls_id: int) -> bool:
        idx = next((i for i, c in enumerate(self.classes) if c.id == cls_id), -1)
        if idx == -1:
            return False
        self.classes.pop(idx)
        for i, c in enumerate(self.classes):
            c.id = i
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

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "image_folder": self.image_folder,
            "image_folders": self.image_folders,
            "classes": [c.to_dict() for c in self.classes],
            "annotations": {fn: ia.to_dict() for fn, ia in self.annotations.items()},
            "current_index": self.current_index,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls()
        p.name = d.get("name", "Untitled Project")
        # Support both new multi-folder and old single-folder format
        image_folders = d.get("image_folders")
        if image_folders:
            p.image_folders = image_folders
            p.image_folder = image_folders[0] if image_folders else ""
        else:
            p.image_folder = d.get("image_folder", "")
            p.image_folders = [p.image_folder] if p.image_folder else []
        p.classes = [ClassDef.from_dict(c) for c in d.get("classes", [])]
        # Migrate old bare-filename annotation keys to absolute paths
        raw = d.get("annotations", {})
        p.annotations = {}
        for k, v in raw.items():
            if not os.path.isabs(k) and p.image_folder:
                abs_k = os.path.normpath(os.path.join(p.image_folder, k))
                ia = ImageAnnotation.from_dict(v)
                ia.filename = abs_k
                p.annotations[abs_k] = ia
            else:
                p.annotations[k] = ImageAnnotation.from_dict(v)
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
        if p.images:
            p.current_index = max(0, min(p.current_index, len(p.images) - 1))
        p.modified = False
        return p

    def load_yolo_labels(self):
        for fn in self.images:
            label_path = str(Path(fn).parent / (Path(fn).stem + ".txt"))
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

    def load_coco_labels(self, coco_json_path: str) -> dict:
        import json as _json

        with open(coco_json_path, encoding="utf-8") as f:
            data = _json.load(f)

        name_to_cls_id: dict[str, int] = {}
        cat_id_to_cls_id: dict[int, int] = {}

        for cat in data.get("categories", []):
            name = cat["name"]
            coco_cat_id = cat["id"]
            if name not in name_to_cls_id:
                name_to_cls_id[name] = len(name_to_cls_id)
            cat_id_to_cls_id[coco_cat_id] = name_to_cls_id[name]

        colors = generate_class_colors(len(name_to_cls_id))
        self.classes = [
            ClassDef(id=cls_id, name=name, color=colors[cls_id])
            for name, cls_id in name_to_cls_id.items()
        ]

        basename_to_info: dict[str, tuple[int, int, int]] = {}
        for img in data.get("images", []):
            bname = Path(img["file_name"]).name.lower()
            basename_to_info[bname] = (img["id"], img.get("width") or 0, img.get("height") or 0)

        anns_by_img: dict[int, list] = {}
        for ann in data.get("annotations", []):
            anns_by_img.setdefault(ann["image_id"], []).append(ann)

        ann_count = 0
        annotated_images = 0

        for fn in self.images:
            bname = Path(fn).name.lower()
            info = basename_to_info.get(bname)
            if info is None:
                continue

            img_id, img_w, img_h = info
            if img_w == 0 or img_h == 0:
                continue

            boxes = []
            for ann in anns_by_img.get(img_id, []):
                cls_id = cat_id_to_cls_id.get(ann["category_id"])
                if cls_id is None:
                    continue

                x, y, bw, bh = ann["bbox"]
                cx = (x + bw / 2.0) / img_w
                cy = (y + bh / 2.0) / img_h
                nw = bw / img_w
                nh = bh / img_h
                cx = max(0.0, min(1.0, cx))
                cy = max(0.0, min(1.0, cy))
                nw = max(0.0, min(1.0, nw))
                nh = max(0.0, min(1.0, nh))
                if nw > 1e-4 and nh > 1e-4:
                    boxes.append(BoundingBox(class_id=cls_id, cx=cx, cy=cy, w=nw, h=nh))
                    ann_count += 1

            if boxes:
                self.annotations[fn] = ImageAnnotation(filename=fn, boxes=boxes)
                annotated_images += 1

        self.modified = True
        self.invalidate_annotated_count()
        return {
            "images_annotated": annotated_images,
            "annotations": ann_count,
            "classes": len(self.classes),
            "total_json_images": len(basename_to_info),
        }
