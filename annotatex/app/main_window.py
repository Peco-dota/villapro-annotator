"""Main application window for AnnotateX."""
from __future__ import annotations
import os
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QStatusBar, QLabel, QProgressBar,
    QMenuBar, QMenu, QMessageBox, QFileDialog,
    QInputDialog, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QAction, QColor

from app.project import Project
from app.annotation import BoundingBox
from app.canvas import AnnotationCanvas
from app.sidebar_images import ImageSidebar
from app.sidebar_classes import ClassesSidebar
from app.toolbar import AnnotateXToolbar
from app.dialogs import (
    ClassAssignDialog, ExportDialog, SettingsDialog, NewProjectDialog, AugmentDialog
)
from app.utils import add_recent_project, remove_recent_project


MAIN_STYLE = """
    QMainWindow {
        background-color: #1a1a2e;
    }
    QStatusBar {
        background-color: #0f172a;
        color: #64748b;
        font-size: 11px;
        border-top: 1px solid #1e293b;
    }
    QMenuBar {
        background-color: #0f172a;
        color: #94a3b8;
        border-bottom: 1px solid #1e293b;
    }
    QMenuBar::item:selected {
        background-color: #1e293b;
        color: #e2e8f0;
    }
    QMenu {
        background-color: #1e293b;
        color: #e2e8f0;
        border: 1px solid #334155;
    }
    QMenu::item:selected {
        background-color: #7c3aed;
    }
    QSplitter::handle {
        background-color: #1e293b;
        width: 2px;
    }
"""


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._auto_save_counter: int = 0
        self._space_pressed: bool = False

        self.setWindowTitle("AnnotateX")
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(MAIN_STYLE)

        self._build_menu()
        self._build_ui()
        self._build_status_bar()
        self._setup_shortcuts()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("File")
        self._act_new = QAction("New Project…", self)
        self._act_new.setShortcut(QKeySequence("Ctrl+N"))
        self._act_new.triggered.connect(self.new_project)
        file_menu.addAction(self._act_new)

        self._act_open = QAction("Open Project…", self)
        self._act_open.setShortcut(QKeySequence("Ctrl+O"))
        self._act_open.triggered.connect(self.open_project)
        file_menu.addAction(self._act_open)

        self._act_save = QAction("Save Project", self)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save.triggered.connect(self.save_project)
        file_menu.addAction(self._act_save)

        self._act_save_as = QAction("Save Project As…", self)
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_save_as.triggered.connect(self.save_project_as)
        file_menu.addAction(self._act_save_as)

        file_menu.addSeparator()

        self._act_export = QAction("Export Dataset…", self)
        self._act_export.triggered.connect(self._show_export)
        file_menu.addAction(self._act_export)

        self._act_augment = QAction("Augment Dataset…", self)
        self._act_augment.triggered.connect(self._show_augment)
        file_menu.addAction(self._act_augment)

        file_menu.addSeparator()

        self._act_settings = QAction("Settings…", self)
        self._act_settings.triggered.connect(self._show_settings)
        file_menu.addAction(self._act_settings)

        file_menu.addSeparator()

        self._act_delete_project = QAction("Delete Project File…", self)
        self._act_delete_project.triggered.connect(self._delete_project_file)
        file_menu.addAction(self._act_delete_project)

        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.setShortcut(QKeySequence("Ctrl+Q"))
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        # Edit
        edit_menu = mb.addMenu("Edit")
        self._act_undo = QAction("Undo", self)
        self._act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self._act_undo.triggered.connect(self._undo)
        edit_menu.addAction(self._act_undo)

        self._act_redo = QAction("Redo", self)
        self._act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        self._act_redo.triggered.connect(self._redo)
        edit_menu.addAction(self._act_redo)

        edit_menu.addSeparator()
        del_act = QAction("Delete Selected Box", self)
        del_act.setShortcut(QKeySequence("Delete"))
        del_act.triggered.connect(lambda: self._canvas.delete_selected() if self._canvas else None)
        edit_menu.addAction(del_act)

        edit_menu.addSeparator()
        copy_prev_act = QAction("Copy Boxes from Previous Image", self)
        copy_prev_act.setShortcut(QKeySequence("C"))
        copy_prev_act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        copy_prev_act.triggered.connect(self._copy_boxes_from_prev)
        edit_menu.addAction(copy_prev_act)

        # View
        view_menu = mb.addMenu("View")
        fit_act = QAction("Fit to Window", self)
        fit_act.setShortcut(QKeySequence("F"))
        fit_act.triggered.connect(lambda: self._canvas.fit_to_window() if self._canvas else None)
        view_menu.addAction(fit_act)

        zoom_100_act = QAction("Zoom 100%", self)
        zoom_100_act.setShortcut(QKeySequence("0"))
        zoom_100_act.triggered.connect(lambda: self._canvas.zoom_100() if self._canvas else None)
        view_menu.addAction(zoom_100_act)

    def _build_ui(self):
        # Toolbar
        self._toolbar = AnnotateXToolbar(self)
        self._toolbar.tool_select.connect(lambda: self._set_tool("select"))
        self._toolbar.tool_draw.connect(lambda: self._set_tool("draw"))
        self._toolbar.zoom_in.connect(lambda: self._canvas.zoom_in() if self._canvas else None)
        self._toolbar.zoom_out.connect(lambda: self._canvas.zoom_out() if self._canvas else None)
        self._toolbar.zoom_fit.connect(lambda: self._canvas.fit_to_window() if self._canvas else None)
        self._toolbar.zoom_100.connect(lambda: self._canvas.zoom_100() if self._canvas else None)
        self._toolbar.undo.connect(self._undo)
        self._toolbar.redo.connect(self._redo)
        self._toolbar.save.connect(self.save_project)
        self._toolbar.export.connect(self._show_export)
        self._toolbar.augment.connect(self._show_augment)
        self._toolbar.prev_image.connect(self._prev_image)
        self._toolbar.next_image.connect(self._next_image)

        # Central area
        central = QWidget()
        self.setCentralWidget(central)
        main_vbox = QVBoxLayout(central)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)
        main_vbox.addWidget(self._toolbar)

        # Content area (sidebars + canvas)
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left sidebar
        self._img_sidebar = ImageSidebar()
        self._img_sidebar.image_selected.connect(self._on_image_selected)
        content_layout.addWidget(self._img_sidebar)

        # Canvas
        self._canvas = AnnotationCanvas()
        self._canvas.box_created.connect(self._on_box_created)
        self._canvas.box_selected.connect(self._on_box_selected)
        self._canvas.box_deleted.connect(self._on_box_deleted)
        self._canvas.box_changed.connect(self._on_box_changed)
        self._canvas.annotations_changed.connect(self._on_annotations_changed)
        self._canvas.zoom_changed.connect(self._on_zoom_changed)
        self._canvas.right_click_box.connect(self._on_right_click_box)
        self._canvas.tool_changed.connect(self._toolbar.set_tool)
        content_layout.addWidget(self._canvas, stretch=1)

        # Right sidebar
        self._cls_sidebar = ClassesSidebar()
        self._cls_sidebar.class_selected.connect(self._on_class_selected)
        self._cls_sidebar.class_added.connect(self._on_class_added)
        self._cls_sidebar.class_deleted.connect(self._on_class_deleted)
        self._cls_sidebar.class_color_changed.connect(self._on_class_color_changed)
        self._cls_sidebar.box_selected.connect(self._on_sidebar_box_selected)
        self._cls_sidebar.box_deleted.connect(self._on_sidebar_box_deleted)
        content_layout.addWidget(self._cls_sidebar)

        main_vbox.addWidget(content, stretch=1)

        # Progress bar (top of canvas area)
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #7c3aed;
            }
        """)
        main_vbox.insertWidget(1, self._progress_bar)

    def _build_status_bar(self):
        sb = self.statusBar()
        sb.setFixedHeight(28)

        self._status_img = QLabel("No project open")
        self._status_zoom = QLabel("Zoom: —")
        self._status_boxes = QLabel("Boxes: —")
        self._status_progress = QLabel("—")

        for lbl in [self._status_img, self._status_zoom,
                    self._status_boxes, self._status_progress]:
            lbl.setStyleSheet("padding: 0 10px; color: #64748b;")

        sb.addWidget(self._status_img)
        sb.addWidget(self._make_status_sep())
        sb.addWidget(self._status_zoom)
        sb.addWidget(self._make_status_sep())
        sb.addWidget(self._status_boxes)
        sb.addWidget(self._make_status_sep())
        sb.addWidget(self._status_progress)

    def _make_status_sep(self) -> QLabel:
        sep = QLabel("|")
        sep.setStyleSheet("color: #334155;")
        return sep

    # ── Shortcuts ─────────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        # Navigation
        QShortcut(QKeySequence("A"), self, self._prev_image)
        QShortcut(QKeySequence("D"), self, self._next_image)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._prev_image)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._next_image)

        # Tool
        QShortcut(QKeySequence("V"), self, lambda: self._set_tool("select"))
        QShortcut(QKeySequence("S"), self, lambda: self._set_tool("select"))
        QShortcut(QKeySequence("R"), self, lambda: self._set_tool("draw"))

        # Class selection 1-9
        for i in range(1, 10):
            idx = i - 1
            QShortcut(QKeySequence(str(i)), self, lambda idx=idx: self._select_class_by_index(idx))

    def _select_class_by_index(self, idx: int):
        if self._project and idx < len(self._project.classes):
            cls = self._project.classes[idx]
            self._on_class_selected(cls.id)

    # ── Project operations ────────────────────────────────────────────────────

    def new_project(self):
        if not self._confirm_unsaved():
            return
        dlg = NewProjectDialog(self)
        if dlg.exec() != NewProjectDialog.DialogCode.Accepted:
            return

        project = Project()
        project.name = dlg.result_name
        project.image_folder = dlg.result_folder

        for name in dlg.result_classes:
            project.add_class(name)

        project.scan_images()

        if hasattr(dlg, 'result_import_labels') and dlg.result_import_labels:
            project.load_yolo_labels()

        # Ask for save location
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", dlg.result_name + ".annotatex",
            "AnnotateX Project (*.annotatex)"
        )
        if path:
            project.save(path)
            add_recent_project(path)

        self._load_project(project)

    def open_project(self):
        if not self._confirm_unsaved():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "AnnotateX Project (*.annotatex)"
        )
        if path:
            self._open_project_file(path)

    def _open_project_file(self, path: str):
        try:
            project = Project.load(path)
            add_recent_project(path)
            self._load_project(project)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    def _load_project(self, project: Project):
        self._project = project
        self.setWindowTitle(f"AnnotateX — {project.name}")

        self._canvas.set_project(project)
        self._img_sidebar.load_project(project)
        self._cls_sidebar.load_project(project)

        # Set default class
        if project.classes:
            self._on_class_selected(project.classes[0].id)

        # Load first image
        if project.images:
            self._navigate_to(project.current_index)

        self._update_progress()
        self._set_tool("draw")

        # Auto-save timer
        self._auto_save_counter = 0

    def save_project(self):
        if not self._project:
            return
        if not self._project.path:
            self.save_project_as()
            return
        try:
            self._project.save()
            self._update_title()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def save_project_as(self):
        if not self._project:
            return
        default = (self._project.name or "project") + ".annotatex"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", default,
            "AnnotateX Project (*.annotatex)"
        )
        if path:
            try:
                self._project.save(path)
                add_recent_project(path)
                self._update_title()
            except Exception as e:
                QMessageBox.critical(self, "Save Error", str(e))

    def _confirm_unsaved(self) -> bool:
        if self._project and self._project.modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before continuing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self.save_project()
                return True
            elif reply == QMessageBox.StandardButton.Cancel:
                return False
        return True

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate_to(self, index: int):
        if not self._project or not self._project.images:
            return
        index = max(0, min(index, len(self._project.images) - 1))
        self._project.current_index = index

        fn = self._project.images[index]
        path = self._project.image_path(fn)

        self._canvas.load_image(path)
        self._img_sidebar.set_current_index(index)
        self._cls_sidebar.refresh_annotations()
        self._update_status(fn)
        self._update_progress()

        # Auto-save
        self._auto_save_counter += 1
        interval = self._project.settings.get("auto_save_interval", 5)
        if self._auto_save_counter >= interval and self._project.path:
            self._auto_save_counter = 0
            self._project.save()

    def _prev_image(self):
        if self._project:
            self._navigate_to(self._project.current_index - 1)

    def _next_image(self):
        if self._project:
            self._navigate_to(self._project.current_index + 1)

    def _copy_boxes_from_prev(self):
        """Copy all bounding boxes from the previous image onto the current image."""
        if not self._project or not self._project.images:
            return
        idx = self._project.current_index
        if idx == 0:
            return  # no previous image
        prev_fn = self._project.images[idx - 1]
        prev_ia = self._project.annotations.get(prev_fn)
        if not prev_ia or not prev_ia.boxes:
            return
        import copy, uuid
        curr_ia = self._project.current_annotation()
        if curr_ia is None:
            return
        self._canvas._push_undo()
        new_ids = []
        for box in prev_ia.boxes:
            new_box = copy.deepcopy(box)
            new_box.id = str(uuid.uuid4())
            new_box.confidence = None
            curr_ia.boxes.append(new_box)
            new_ids.append(new_box.id)
        self._project.modified = True
        self._project.invalidate_annotated_count()
        self._canvas.reload_annotations()
        # Select all copied boxes so handles are visible and draggable
        for i, bid in enumerate(new_ids):
            self._canvas.select_box(bid, multi=(i > 0))
        self._canvas.annotations_changed.emit()

    def _on_image_selected(self, index: int):
        if self._project:
            self._navigate_to(index)

    # ── Canvas event handlers ──────────────────────────────────────────────────

    def _on_box_created(self, box: BoundingBox):
        """Show class assignment dialog, then commit."""
        if not self._project:
            return
        if not self._project.classes:
            QMessageBox.information(
                self, "No Classes",
                "Please add at least one class before annotating."
            )
            return
        dlg = ClassAssignDialog(
            self._project.classes,
            self._canvas._current_class_id,
            self
        )
        if dlg.exec() == ClassAssignDialog.DialogCode.Accepted:
            box.class_id = dlg.selected_class_id
            self._canvas.commit_box(box)
            self._cls_sidebar.refresh_annotations()
            self._img_sidebar.refresh_item(
                self._project.current_image_filename() or ""
            )
            self._update_status_boxes()

    def _on_box_selected(self, box):
        if box:
            self._cls_sidebar.highlight_box(box.id)
        else:
            self._cls_sidebar.highlight_box(None)

    def _on_box_deleted(self, box_id: str):
        self._cls_sidebar.refresh_annotations()
        if self._project:
            fn = self._project.current_image_filename()
            if fn:
                self._img_sidebar.refresh_item(fn)
        self._update_status_boxes()

    def _on_box_changed(self, box):
        self._cls_sidebar.refresh_annotations()

    def _on_annotations_changed(self):
        if self._project:
            self._project.invalidate_annotated_count()
        self._cls_sidebar.refresh_annotations()
        self._cls_sidebar.update_class_counts()
        if self._project:
            fn = self._project.current_image_filename()
            if fn:
                self._img_sidebar.refresh_item(fn)
        self._update_status_boxes()
        self._update_progress()

    def _on_zoom_changed(self, zoom: float):
        self._status_zoom.setText(f"Zoom: {int(zoom * 100)}%")

    def _on_right_click_box(self, box: BoundingBox, global_pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
            }
            QMenu::item:selected { background-color: #7c3aed; }
        """)

        change_act = menu.addAction("Change Class")
        delete_act = menu.addAction("Delete Box")

        action = menu.exec(global_pos)
        if action == change_act:
            self._change_box_class(box)
        elif action == delete_act:
            self._canvas.select_box(box.id)
            self._canvas.delete_selected()

    def _change_box_class(self, box: BoundingBox):
        if not self._project or not self._project.classes:
            return
        dlg = ClassAssignDialog(self._project.classes, box.class_id, self)
        if dlg.exec() == ClassAssignDialog.DialogCode.Accepted:
            box.class_id = dlg.selected_class_id
            self._canvas.update_annotation_item(box.id)
            self._cls_sidebar.refresh_annotations()
            if self._project:
                self._project.modified = True
            self._canvas.reload_annotations()

    # ── Sidebar event handlers ────────────────────────────────────────────────

    def _on_class_selected(self, cls_id: int):
        self._canvas.set_current_class(cls_id)
        self._cls_sidebar.set_active_class(cls_id)

    def _on_class_added(self, name: str):
        if not self._project:
            return
        cls = self._project.add_class(name)
        self._cls_sidebar.refresh_classes()
        self._on_class_selected(cls.id)

    def _on_class_deleted(self, cls_id: int):
        if not self._project:
            return
        self._project.remove_class(cls_id)
        self._project.invalidate_annotated_count()
        self._cls_sidebar.refresh_classes()
        self._cls_sidebar.refresh_annotations()
        self._canvas.reload_annotations()
        if self._project.classes:
            self._on_class_selected(self._project.classes[0].id)
        self._img_sidebar.refresh_all_badges()

    def _on_class_color_changed(self, cls_id: int, color: str):
        self._canvas.reload_annotations()

    def _on_sidebar_box_selected(self, box_id: str):
        self._canvas.select_box(box_id)

    def _on_sidebar_box_deleted(self, box_id: str):
        self._canvas.select_box(box_id)
        self._canvas.delete_selected()

    # ── Tool ──────────────────────────────────────────────────────────────────

    def _set_tool(self, tool: str):
        self._canvas.set_tool(tool)
        self._toolbar.set_tool(tool)

    # ── Undo/Redo ────────────────────────────────────────────────────────────

    def _undo(self):
        self._canvas.undo()
        self._cls_sidebar.refresh_annotations()
        self._update_status_boxes()
        self._update_progress()

    def _redo(self):
        self._canvas.redo()
        self._cls_sidebar.refresh_annotations()
        self._update_status_boxes()
        self._update_progress()

    # ── Status updates ────────────────────────────────────────────────────────

    def _update_status(self, filename: str):
        self._status_img.setText(f"Image: {filename}")
        self._update_status_boxes()

    def _update_status_boxes(self):
        if self._project:
            ia = self._project.current_annotation()
            count = ia.box_count if ia else 0
            self._status_boxes.setText(f"Boxes: {count}")

    def _update_progress(self):
        if not self._project:
            return
        annotated = self._project.annotated_count
        total = self._project.total_count
        self._status_progress.setText(f"{annotated} / {total} annotated")
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(annotated)

    def _update_title(self):
        if self._project:
            mod = " *" if self._project.modified else ""
            self.setWindowTitle(f"AnnotateX — {self._project.name}{mod}")

    # ── Dialogs ───────────────────────────────────────────────────────────────

    def _show_export(self):
        if not self._project:
            QMessageBox.information(self, "No Project", "Please open a project first.")
            return
        dlg = ExportDialog(self._project, self)
        dlg.exec()

    def _show_augment(self):
        if not self._project:
            QMessageBox.information(self, "No Project", "Please open a project first.")
            return
        dlg = AugmentDialog(self._project, self)
        dlg.exec()

    def _delete_project_file(self):
        if not self._project or not self._project.path:
            QMessageBox.information(self, "Delete Project", "Project has not been saved to disk yet.")
            return
        path = self._project.path
        name = os.path.basename(path)
        reply = QMessageBox.warning(
            self,
            "Delete Project",
            f"Delete '{name}' from disk?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not delete file:\n{e}")
            return
        remove_recent_project(path)
        self._project.path = None
        self._project.modified = False
        self._update_title()

    def _show_settings(self):
        if not self._project:
            return
        dlg = SettingsDialog(self._project, self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self._canvas.set_opacity(self._project.settings.get("annotation_opacity", 0.15))
            from PyQt6.QtGui import QBrush, QColor
            self._canvas.setBackgroundBrush(
                QBrush(QColor(self._project.settings.get("canvas_bg", "#2a2a2a")))
            )

    # ── Window events ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if not self._confirm_unsaved():
            event.ignore()
            return
        event.accept()

    def keyPressEvent(self, event):
        # Don't swallow shortcuts when canvas is focused
        super().keyPressEvent(event)
