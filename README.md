# AnnotateX

Professional YOLO dataset annotation desktop application built with PyQt6.

## Setup

```bash
# 1. Create and activate virtual environment (already done)
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 2. Install dependencies
pip install -r annotatex/requirements.txt

# 3. Run
cd annotatex
python main.py

# Optional: open a project directly
python main.py /path/to/project.annotatex
```

## Features

- **Project management** — create/open/save `.annotatex` project files with full state
- **Image navigation** — thumbnail sidebar, keyboard nav, progress tracking
- **Annotation canvas** — zoomable/pannable QGraphicsView with precise bbox drawing
- **Classes panel** — add/remove/reorder classes with auto-assigned colors
- **Annotations panel** — per-image box list with click-to-select
- **YOLO export** — `images/`, `labels/`, `classes.txt`, optional `data.yaml` + train/val/test split
- **COCO JSON export** — standard COCO format
- **Undo/Redo** — full history stack per image
- **Auto-save** — configurable interval
- **Dark theme** — Roboflow-inspired dark UI

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `A` / `←` | Previous image |
| `D` / `→` | Next image |
| `R` | Draw rectangle tool |
| `V` / `S` | Select/move tool |
| `1`–`9` | Select class by index |
| `Delete` | Delete selected box |
| `Escape` | Deselect |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Redo |
| `Ctrl+S` | Save project |
| `Ctrl+N` | New project |
| `Ctrl+O` | Open project |
| `F` | Fit image to window |
| `0` | Zoom to 100% |
| `+` / `-` | Zoom in / out |
| `Ctrl+Scroll` | Zoom in/out |
| `Middle mouse` / `Space+drag` | Pan canvas |

## Project File Format

Projects are saved as `.annotatex` JSON files containing:
- Image folder path
- Class definitions (name + color)
- All bounding box annotations (normalized YOLO coords)
- Current image index and settings

## Export Formats

### YOLO
```
output/
├── train/
│   ├── images/
│   └── labels/
├── val/
│   ├── images/
│   └── labels/
├── test/
│   ├── images/
│   └── labels/
├── classes.txt
└── data.yaml
```

Each label file contains one line per box:
```
class_id cx cy width height
```
All values normalized 0–1.

### COCO JSON
```
output/
├── images/
└── annotations.json
```

## File Structure

```
annotatex/
├── main.py                 # Entry point + welcome screen
├── requirements.txt
└── app/
    ├── annotation.py       # BoundingBox & ClassDef data structures
    ├── project.py          # Project model, serialization, YOLO I/O
    ├── utils.py            # Colors, YOLO/COCO export, helpers
    ├── canvas.py           # QGraphicsView annotation canvas
    ├── sidebar_images.py   # Left image thumbnail list
    ├── sidebar_classes.py  # Right classes + annotations panel
    ├── toolbar.py          # Top toolbar
    ├── dialogs.py          # Export, settings, new project, class assign
    └── main_window.py      # Main QMainWindow
```
