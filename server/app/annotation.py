"""Annotation data structures for AnnotateX."""
from dataclasses import dataclass, field
from typing import Optional
import uuid


@dataclass
class BoundingBox:
    """A single bounding box annotation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    class_id: int = 0
    # Normalized YOLO coords (0-1)
    cx: float = 0.0
    cy: float = 0.0
    w: float = 0.0
    h: float = 0.0
    confidence: Optional[float] = None

    def to_pixel(self, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        """Return (x1, y1, x2, y2) in pixel coords."""
        x1 = int((self.cx - self.w / 2) * img_w)
        y1 = int((self.cy - self.h / 2) * img_h)
        x2 = int((self.cx + self.w / 2) * img_w)
        y2 = int((self.cy + self.h / 2) * img_h)
        return x1, y1, x2, y2

    def to_pixel_xywh(self, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        """Return (x, y, width, height) in pixel coords."""
        x = int((self.cx - self.w / 2) * img_w)
        y = int((self.cy - self.h / 2) * img_h)
        w = int(self.w * img_w)
        h = int(self.h * img_h)
        return x, y, w, h

    @classmethod
    def from_pixel(cls, x1: float, y1: float, x2: float, y2: float,
                   img_w: int, img_h: int, class_id: int = 0) -> "BoundingBox":
        """Create from pixel coordinates."""
        # Clamp to image bounds
        x1 = max(0.0, min(float(x1), float(img_w)))
        y1 = max(0.0, min(float(y1), float(img_h)))
        x2 = max(0.0, min(float(x2), float(img_w)))
        y2 = max(0.0, min(float(y2), float(img_h)))
        # Ensure x1<x2, y1<y2
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        cx = ((x1 + x2) / 2) / img_w
        cy = ((y1 + y2) / 2) / img_h
        w = (x2 - x1) / img_w
        h = (y2 - y1) / img_h
        return cls(class_id=class_id, cx=cx, cy=cy, w=w, h=h)

    def is_valid(self) -> bool:
        """Check the box has non-zero area and is in bounds."""
        return (self.w > 1e-6 and self.h > 1e-6 and
                0 <= self.cx <= 1 and 0 <= self.cy <= 1 and
                0 < self.w <= 1 and 0 < self.h <= 1)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "class_index": self.class_id,
            "cx": self.cx,
            "cy": self.cy,
            "w": self.w,
            "h": self.h,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BoundingBox":
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            class_id=d.get("class_index", d.get("class_id", 0)),
            cx=d.get("cx", 0.0),
            cy=d.get("cy", 0.0),
            w=d.get("w", 0.0),
            h=d.get("h", 0.0),
            confidence=d.get("confidence"),
        )

    def to_yolo_line(self) -> str:
        return f"{self.class_id} {self.cx:.6f} {self.cy:.6f} {self.w:.6f} {self.h:.6f}"


@dataclass
class ClassDef:
    """A class definition."""
    id: int = 0
    name: str = "class"
    color: str = "#7c3aed"  # hex color

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color}

    @classmethod
    def from_dict(cls, d: dict) -> "ClassDef":
        return cls(id=d["id"], name=d["name"], color=d.get("color", "#7c3aed"))
