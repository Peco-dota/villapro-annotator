"""Detection Service Manager dialog for VisionQ."""
from __future__ import annotations

import webbrowser

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QDoubleSpinBox, QFileDialog, QFormLayout, QWidget,
    QScrollArea, QFrame, QMessageBox, QSizePolicy, QCheckBox,
    QTextEdit, QMenu, QGroupBox, QSlider,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QAction, QImage, QPixmap

from app.detection_service import (
    get_registry, ServiceConfig,
    STATE_STOPPED, STATE_LOADING, STATE_RUNNING, STATE_ERROR,
)
from app.result_receiver import get_receiver

# ── Shared styles ──────────────────────────────────────────────────────────────

_BASE = """
    QDialog, QWidget {
        background-color: #1a1a2e;
        color: #e2e8f0;
    }
    QLabel { color: #94a3b8; font-size: 12px; }
    QLineEdit, QSpinBox, QDoubleSpinBox {
        background-color: #0f172a;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #7c3aed; }
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        background-color: #1e293b; border: none; width: 16px;
    }
    QScrollArea { background: transparent; border: none; }
    QCheckBox { color: #94a3b8; font-size: 12px; }
    QCheckBox::indicator {
        width: 14px; height: 14px;
        border: 1px solid #334155;
        border-radius: 3px;
        background: #0f172a;
    }
    QCheckBox::indicator:checked {
        background: #7c3aed;
        border-color: #7c3aed;
    }
    QTextEdit {
        background-color: #0a0f1e;
        color: #4ade80;
        border: 1px solid #1e293b;
        border-radius: 6px;
        font-family: monospace;
        font-size: 10px;
        padding: 4px 6px;
    }
    QGroupBox {
        color: #64748b;
        font-size: 11px;
        font-weight: bold;
        border: 1px solid #1e293b;
        border-radius: 6px;
        margin-top: 8px;
        padding-top: 6px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 6px;
        left: 10px;
    }
"""

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _btn(label: str, color: str, hover: str, text_color: str = "white",
         border_color: str = "") -> QPushButton:
    b = QPushButton(label)
    border_css = f"border: 1px solid {border_color};" if border_color else "border: none;"
    b.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: {text_color};
            {border_css}
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            padding: 5px 12px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:disabled {{ background-color: #1e293b; color: #475569; border: none; }}
    """)
    return b


# ── Config dialog (add / edit / relaunch) ──────────────────────────────────────

class ServiceConfigDialog(QDialog):
    """Popup for entering, editing, or duplicating a service config."""

    def __init__(self, cfg: ServiceConfig | None = None, parent=None, is_duplicate: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Configure Service")
        self.setMinimumWidth(480)
        self.setStyleSheet(_BASE)
        self._result_cfg: ServiceConfig | None = None
        self._is_duplicate = is_duplicate
        self._build_ui(cfg)

    def _build_ui(self, cfg: ServiceConfig | None):
        # Outer layout: scrollable content + pinned button row
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        _content = QWidget()
        layout = QVBoxLayout(_content)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 12)

        scroll.setWidget(_content)
        outer.addWidget(scroll, stretch=1)

        # Limit dialog height to available screen so it never goes off-screen
        from PyQt6.QtWidgets import QApplication
        available = QApplication.primaryScreen().availableGeometry()
        self.setMaximumHeight(available.height() - 40)

        if self._is_duplicate:
            title_text = f"Duplicate — {cfg.name}" if cfg else "Duplicate Service"
        elif cfg is None:
            title_text = "New Service"
        else:
            title_text = f"Edit — {cfg.name}"
        title = QLabel(title_text)
        title.setStyleSheet("color: #a78bfa; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name — editable for new and duplicate, locked for plain edit
        self._name = QLineEdit(cfg.name if cfg else "")
        self._name.setPlaceholderText("e.g. gate_1_in, gate_2_out…")
        if cfg and not self._is_duplicate:
            self._name.setEnabled(False)
        form.addRow("Name:", self._name)

        # Model
        model_row = QHBoxLayout()
        self._model = QLineEdit(cfg.model_path if cfg else "")
        self._model.setPlaceholderText("Path to .pt weights file…")
        browse = _btn("Browse…", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        browse.setFixedWidth(72)
        browse.clicked.connect(self._browse)
        model_row.addWidget(self._model)
        model_row.addWidget(browse)
        form.addRow("Model:", model_row)

        layout.addLayout(form)

        # ── Input source group ─────────────────────────────────────────────────
        input_group = QGroupBox("Input Source")
        input_group.setStyleSheet(_BASE)
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)
        input_layout.setContentsMargins(10, 14, 10, 10)

        input_mode = (cfg.input_mode if cfg and cfg.input_mode in ("http", "rtsp", "video")
                      else ("rtsp" if cfg and cfg.rtsp_enabled else "http"))

        self._rtsp_chk = QCheckBox("Use RTSP camera stream (instead of HTTP endpoint)")
        self._rtsp_chk.setChecked(input_mode == "rtsp")
        self._rtsp_chk.toggled.connect(self._on_rtsp_toggled)
        input_layout.addWidget(self._rtsp_chk)

        self._video_chk = QCheckBox("Use local video file as input (simulate live stream)")
        self._video_chk.setChecked(input_mode == "video")
        self._video_chk.toggled.connect(self._on_video_toggled)
        input_layout.addWidget(self._video_chk)

        # HTTP section
        self._http_widget = QWidget()
        self._http_widget.setStyleSheet("background: transparent;")
        http_form = QFormLayout(self._http_widget)
        http_form.setSpacing(8)
        http_form.setContentsMargins(0, 4, 0, 0)
        http_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._in_host = QLineEdit(cfg.input_host if cfg else "0.0.0.0")
        http_form.addRow("Listen host:", self._in_host)
        self._in_port = QSpinBox()
        self._in_port.setRange(1024, 65535)
        self._in_port.setValue(cfg.input_port if cfg else 5050)
        http_form.addRow("Listen port:", self._in_port)

        input_layout.addWidget(self._http_widget)

        # RTSP section
        self._rtsp_widget = QWidget()
        self._rtsp_widget.setStyleSheet("background: transparent;")
        rtsp_form = QFormLayout(self._rtsp_widget)
        rtsp_form.setSpacing(8)
        rtsp_form.setContentsMargins(0, 4, 0, 0)
        rtsp_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._rtsp_user = QLineEdit(cfg.rtsp_user if cfg else "admin")
        self._rtsp_user.setPlaceholderText("Camera username")
        rtsp_form.addRow("Username:", self._rtsp_user)

        self._rtsp_pass = QLineEdit(cfg.rtsp_password if cfg else "")
        self._rtsp_pass.setPlaceholderText("Camera password")
        self._rtsp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        rtsp_form.addRow("Password:", self._rtsp_pass)

        self._rtsp_ip = QLineEdit(cfg.rtsp_ip if cfg else "192.168.1.1")
        self._rtsp_ip.setPlaceholderText("e.g. 192.168.78.7")
        rtsp_form.addRow("Camera IP:", self._rtsp_ip)

        self._rtsp_port = QSpinBox()
        self._rtsp_port.setRange(1, 65535)
        self._rtsp_port.setValue(cfg.rtsp_port if cfg else 554)
        rtsp_form.addRow("RTSP port:", self._rtsp_port)

        self._rtsp_channel = QLineEdit(cfg.rtsp_channel if cfg else "Streaming/Channels/102")
        self._rtsp_channel.setPlaceholderText("e.g. Streaming/Channels/102")
        rtsp_form.addRow("Channel path:", self._rtsp_channel)

        self._rtsp_interval = QDoubleSpinBox()
        self._rtsp_interval.setRange(0.05, 10.0)
        self._rtsp_interval.setSingleStep(0.05)
        self._rtsp_interval.setDecimals(2)
        self._rtsp_interval.setSuffix(" s")
        self._rtsp_interval.setValue(cfg.rtsp_interval if cfg else 0.25)
        rtsp_form.addRow("Frame interval:", self._rtsp_interval)

        # URL preview
        self._url_preview = QLabel()
        self._url_preview.setStyleSheet(
            "color: #475569; font-size: 10px; font-family: monospace; "
            "background: #0a0f1e; border-radius: 4px; padding: 4px 6px;"
        )
        self._url_preview.setWordWrap(True)
        rtsp_form.addRow("Stream URL:", self._url_preview)

        # Update preview on any RTSP field change
        for widget in (self._rtsp_user, self._rtsp_pass, self._rtsp_ip, self._rtsp_channel):
            widget.textChanged.connect(self._update_url_preview)
        self._rtsp_port.valueChanged.connect(self._update_url_preview)

        input_layout.addWidget(self._rtsp_widget)

        # Video-file section
        self._video_widget = QWidget()
        self._video_widget.setStyleSheet("background: transparent;")
        video_form = QFormLayout(self._video_widget)
        video_form.setSpacing(8)
        video_form.setContentsMargins(0, 4, 0, 0)
        video_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        video_row = QHBoxLayout()
        self._video_path = QLineEdit(cfg.video_path if cfg else "")
        self._video_path.setPlaceholderText("Select .mp4 / .avi / .mov video file…")
        video_row.addWidget(self._video_path)
        browse_video = _btn("Browse", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        browse_video.setFixedWidth(70)
        browse_video.clicked.connect(self._browse_video)
        video_row.addWidget(browse_video)
        video_form.addRow("Video file:", video_row)

        self._video_interval = QDoubleSpinBox()
        self._video_interval.setRange(0.05, 10.0)
        self._video_interval.setSingleStep(0.05)
        self._video_interval.setDecimals(2)
        self._video_interval.setSuffix(" s")
        self._video_interval.setValue(cfg.rtsp_interval if cfg else 0.25)
        video_form.addRow("Frame interval:", self._video_interval)

        self._video_loop = QCheckBox("Loop video when it ends")
        self._video_loop.setChecked(cfg.video_loop if cfg else True)
        video_form.addRow("", self._video_loop)

        input_layout.addWidget(self._video_widget)
        layout.addWidget(input_group)

        # ── Output group ───────────────────────────────────────────────────────
        output_group = QGroupBox("Result Output")
        output_group.setStyleSheet(_BASE)
        out_form = QFormLayout(output_group)
        out_form.setSpacing(8)
        out_form.setContentsMargins(10, 14, 10, 10)
        out_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        hint = QLabel("Detection results (JSON) are pushed via HTTP POST to:")
        hint.setStyleSheet("color: #475569; font-size: 11px;")
        out_form.addRow("", hint)

        self._out_host = QLineEdit(cfg.output_host if cfg else "127.0.0.1")
        out_form.addRow("Output host:", self._out_host)
        self._out_port = QSpinBox()
        self._out_port.setRange(1, 65535)
        self._out_port.setValue(cfg.output_port if cfg else 6060)
        out_form.addRow("Output port:", self._out_port)

        layout.addWidget(output_group)

        # ── Detection settings group ───────────────────────────────────────────
        det_group = QGroupBox("Detection Settings")
        det_group.setStyleSheet(_BASE)
        det_form = QFormLayout(det_group)
        det_form.setSpacing(8)
        det_form.setContentsMargins(10, 14, 10, 10)
        det_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._conf_threshold = QDoubleSpinBox()
        self._conf_threshold.setRange(0.01, 1.0)
        self._conf_threshold.setSingleStep(0.05)
        self._conf_threshold.setDecimals(2)
        self._conf_threshold.setValue(cfg.conf_threshold if cfg else 0.5)
        det_form.addRow("Confidence threshold:", self._conf_threshold)

        self._strict_output = QCheckBox(
            "Strict output: emit forward/idle/backward when car present, no_car when absent"
        )
        self._strict_output.setChecked(cfg.strict_output if cfg else False)
        det_form.addRow("", self._strict_output)

        self._state_changes_only = QCheckBox(
            "State changes only: emit once per transition (forward → idle → no_car…)"
        )
        self._state_changes_only.setChecked(cfg.state_changes_only if cfg else False)
        det_form.addRow("", self._state_changes_only)

        layout.addWidget(det_group)

        # ── Dataset capture group ──────────────────────────────────────────────
        ds_group = QGroupBox("Dataset Capture")
        ds_group.setStyleSheet(_BASE)
        ds_form = QFormLayout(ds_group)
        ds_form.setSpacing(8)
        ds_form.setContentsMargins(10, 14, 10, 10)
        ds_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._dataset_capture = QCheckBox("Save raw frames for annotation")
        self._dataset_capture.setChecked(cfg.dataset_capture if cfg else False)
        self._dataset_capture.toggled.connect(self._on_dataset_capture_toggled)
        ds_form.addRow("", self._dataset_capture)

        self._dataset_interval = QSpinBox()
        self._dataset_interval.setRange(1, 1000)
        self._dataset_interval.setValue(cfg.dataset_interval if cfg else 10)
        self._dataset_interval.setSuffix(" frames")
        ds_form.addRow("Capture every:", self._dataset_interval)

        ds_dir_row = QHBoxLayout()
        self._dataset_dir = QLineEdit(cfg.dataset_dir if cfg else "")
        self._dataset_dir.setPlaceholderText("Leave blank to use frames_dir/dataset/")
        ds_dir_row.addWidget(self._dataset_dir)
        browse_ds = _btn("Browse", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        browse_ds.setFixedWidth(70)
        browse_ds.clicked.connect(self._browse_dataset_dir)
        ds_dir_row.addWidget(browse_ds)
        ds_form.addRow("Output folder:", ds_dir_row)

        self._on_dataset_capture_toggled(self._dataset_capture.isChecked())
        layout.addWidget(ds_group)

        # ── Stream recording group ───────────────────────────────────────────
        rec_group = QGroupBox("Input Recording")
        rec_group.setStyleSheet(_BASE)
        rec_form = QFormLayout(rec_group)
        rec_form.setSpacing(8)
        rec_form.setContentsMargins(10, 14, 10, 10)
        rec_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._record_stream = QCheckBox("Auto-start raw recording to MP4 when service starts")
        self._record_stream.setChecked(cfg.record_stream if cfg else False)
        self._record_stream.toggled.connect(self._on_record_toggled)
        rec_form.addRow("", self._record_stream)

        fps_hint = QLabel("Recording FPS is set automatically from the frame interval above.")
        fps_hint.setStyleSheet("color: #475569; font-size: 10px;")
        rec_form.addRow("", fps_hint)

        rec_dir_row = QHBoxLayout()
        self._record_dir = QLineEdit(cfg.record_dir if cfg else "")
        self._record_dir.setPlaceholderText("Leave blank to use ~/VisionQ_recordings/")
        rec_dir_row.addWidget(self._record_dir)
        browse_rec = _btn("Browse", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        browse_rec.setFixedWidth(70)
        browse_rec.clicked.connect(self._browse_record_dir)
        rec_dir_row.addWidget(browse_rec)
        rec_form.addRow("Output folder:", rec_dir_row)

        self._record_group = rec_group
        self._on_record_toggled(self._record_stream.isChecked())
        layout.addWidget(rec_group)

        # Auto-start (last item in scroll content)
        self._auto_start = QCheckBox("Auto-start this service when VisionQ opens")
        self._auto_start.setChecked(cfg.auto_start if cfg else False)
        layout.addWidget(self._auto_start)

        # Button row — outside the scroll, always visible at the bottom
        btn_container = QWidget()
        btn_container.setStyleSheet("background-color: #1a1a2e; border-top: 1px solid #1e293b;")
        btn_row = QHBoxLayout(btn_container)
        btn_row.setContentsMargins(20, 10, 20, 14)
        btn_row.addStretch()
        cancel = _btn("Cancel", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        ok = _btn("▶  Save & Start", "#7c3aed", "#6d28d9")
        ok.clicked.connect(self._accept)
        btn_row.addWidget(ok)
        outer.addWidget(btn_container)

        # Initial state
        self._apply_input_mode()
        self._on_record_toggled(self._record_stream.isChecked())
        self._update_url_preview()

    def _on_rtsp_toggled(self, checked: bool):
        if checked and self._video_chk.isChecked():
            self._video_chk.setChecked(False)
            return
        self._apply_input_mode()

    def _on_video_toggled(self, checked: bool):
        if checked and self._rtsp_chk.isChecked():
            self._rtsp_chk.setChecked(False)
            return
        self._apply_input_mode()

    def _current_input_mode(self) -> str:
        if self._video_chk.isChecked():
            return "video"
        if self._rtsp_chk.isChecked():
            return "rtsp"
        return "http"

    def _apply_input_mode(self):
        mode = self._current_input_mode()
        self._http_widget.setVisible(mode == "http")
        self._rtsp_widget.setVisible(mode == "rtsp")
        self._video_widget.setVisible(mode == "video")
        self._record_group.setVisible(mode in ("rtsp", "video"))

    def _on_dataset_capture_toggled(self, checked: bool):
        self._dataset_interval.setEnabled(checked)
        self._dataset_dir.setEnabled(checked)

    def _on_record_toggled(self, checked: bool):
        self._record_dir.setEnabled(checked)

    def _browse_dataset_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Dataset Output Folder", self._dataset_dir.text()
        )
        if folder:
            self._dataset_dir.setText(folder)

    def _browse_record_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Video Recording Output Folder", self._record_dir.text()
        )
        if folder:
            self._record_dir.setText(folder)

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Input Video",
            self._video_path.text(),
            "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)",
        )
        if path:
            self._video_path.setText(path)

    def _update_url_preview(self):
        user = self._rtsp_user.text().strip()
        password = self._rtsp_pass.text()
        ip = self._rtsp_ip.text().strip()
        port = self._rtsp_port.value()
        channel = self._rtsp_channel.text().strip().lstrip("/")
        auth = f"{user}:{password}@" if user else ""
        url = f"rtsp://{auth}{ip}:{port}/{channel}"
        self._url_preview.setText(url)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select YOLO Weights", "", "YOLO Weights (*.pt)"
        )
        if path:
            self._model.setText(path)

    def _accept(self):
        name = self._name.text().strip()
        model = self._model.text().strip()
        mode = self._current_input_mode()

        if not name:
            QMessageBox.warning(self, "Validation", "Service name is required.")
            return
        if not model:
            QMessageBox.warning(self, "Validation", "Model path is required.")
            return
        import os
        if not os.path.isfile(model):
            QMessageBox.warning(self, "Model Not Found",
                                f"Model file does not exist:\n{model}")
            return

        if mode == "rtsp":
            if not self._rtsp_ip.text().strip():
                QMessageBox.warning(self, "Validation", "Camera IP address is required.")
                return
            if not self._rtsp_user.text().strip():
                QMessageBox.warning(self, "Validation", "Camera username is required.")
                return

        if mode == "video":
            video_path = self._video_path.text().strip()
            if not video_path:
                QMessageBox.warning(self, "Validation", "Video file path is required for video input mode.")
                return
            if not os.path.isfile(video_path):
                QMessageBox.warning(self, "Validation", f"Video file not found:\n{video_path}")
                return

        interval = self._rtsp_interval.value() if mode == "rtsp" else self._video_interval.value()

        self._result_cfg = ServiceConfig(
            name=name,
            model_path=model,
            input_host=self._in_host.text().strip() or "0.0.0.0",
            input_port=self._in_port.value(),
            output_host=self._out_host.text().strip() or "127.0.0.1",
            output_port=self._out_port.value(),
            input_mode=mode,
            auto_start=self._auto_start.isChecked(),
            rtsp_enabled=(mode == "rtsp"),
            rtsp_user=self._rtsp_user.text().strip(),
            rtsp_password=self._rtsp_pass.text(),
            rtsp_ip=self._rtsp_ip.text().strip(),
            rtsp_port=self._rtsp_port.value(),
            rtsp_channel=self._rtsp_channel.text().strip().lstrip("/"),
            rtsp_interval=interval,
            video_path=self._video_path.text().strip(),
            video_loop=self._video_loop.isChecked(),
            conf_threshold=self._conf_threshold.value(),
            strict_output=self._strict_output.isChecked(),
            state_changes_only=self._state_changes_only.isChecked(),
            dataset_capture=self._dataset_capture.isChecked(),
            dataset_interval=self._dataset_interval.value(),
            dataset_dir=self._dataset_dir.text().strip(),
            record_stream=self._record_stream.isChecked() and mode in ("rtsp", "video"),
            record_dir=self._record_dir.text().strip(),
        )
        self.accept()

    @property
    def result_config(self) -> ServiceConfig | None:
        return self._result_cfg


# ── Live preview dialog ────────────────────────────────────────────────────────

class PreviewDialog(QDialog):
    """Floating window that displays annotated frames from a running service.

    In video mode an extra controls bar is shown at the bottom with:
      • rewind buttons (-5 s / -15 s)
      • speed buttons (0.5× / 1× / 2× / 4×)
      • a progress slider + current/total time label
    """

    closed = pyqtSignal()
    # Seek buttons emit delta in seconds (negative = rewind, positive = forward)
    seek_delta_requested = pyqtSignal(float)
    # Slider release emits absolute position in ms
    seek_to_ms_requested = pyqtSignal(float)
    # Speed buttons
    speed_requested = pyqtSignal(float)
    # Pause / play toggle
    pause_toggled = pyqtSignal()
    # Step one frame while paused
    step_frame_requested = pyqtSignal()

    def __init__(self, service_name: str, is_video: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Preview — {service_name}")
        self.setStyleSheet("background: #0a0f1e;")
        self.setMinimumSize(480, 320)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Video frame area ──────────────────────────────────────────────────
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background: #0a0f1e; color: #334155;")
        self._label.setText("Waiting for first frame…")
        layout.addWidget(self._label, stretch=1)

        # ── Controls bar (video mode only) ───────────────────────────────────
        self._controls = QWidget()
        self._controls.setStyleSheet("background: #0f172a; border-top: 1px solid #1e293b;")
        ctrl = QVBoxLayout(self._controls)
        ctrl.setContentsMargins(12, 8, 12, 10)
        ctrl.setSpacing(6)

        # Progress slider row
        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 10000)
        self._slider.setValue(0)
        self._slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px; background: #334155; border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #7c3aed; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px; height: 14px;
                background: #a78bfa; border-radius: 7px;
                margin: -5px 0;
            }
        """)
        self._slider_dragging = False
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        prog_row.addWidget(self._slider, stretch=1)

        self._time_lbl = QLabel("0:00 / 0:00")
        self._time_lbl.setStyleSheet("color: #64748b; font-size: 10px; min-width: 95px;")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        prog_row.addWidget(self._time_lbl)
        ctrl.addLayout(prog_row)

        # Buttons row: navigation | spacer | speed | step
        btn_row = QHBoxLayout()
        btn_row.setSpacing(5)

        # Go to start
        go_start = _btn("⏮", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        go_start.setFixedWidth(36)
        go_start.setToolTip("Go to beginning")
        go_start.clicked.connect(lambda: self.seek_to_ms_requested.emit(0.0))
        btn_row.addWidget(go_start)

        # Rewind
        rw15 = _btn("-15s", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        rw15.setFixedWidth(48)
        rw15.setToolTip("Rewind 15 seconds")
        rw15.clicked.connect(lambda: self.seek_delta_requested.emit(-15.0))
        btn_row.addWidget(rw15)

        rw5 = _btn("-5s", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        rw5.setFixedWidth(44)
        rw5.setToolTip("Rewind 5 seconds")
        rw5.clicked.connect(lambda: self.seek_delta_requested.emit(-5.0))
        btn_row.addWidget(rw5)

        # Pause / Play
        self._play_btn = _btn("⏸", "#1e293b", "#334155", "#60a5fa", border_color="#334155")
        self._play_btn.setFixedWidth(38)
        self._play_btn.setToolTip("Pause / Play")
        self._play_btn.clicked.connect(lambda: self.pause_toggled.emit())
        btn_row.addWidget(self._play_btn)

        # Forward
        fw5 = _btn("+5s", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        fw5.setFixedWidth(44)
        fw5.setToolTip("Skip forward 5 seconds")
        fw5.clicked.connect(lambda: self.seek_delta_requested.emit(5.0))
        btn_row.addWidget(fw5)

        fw15 = _btn("+15s", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        fw15.setFixedWidth(48)
        fw15.setToolTip("Skip forward 15 seconds")
        fw15.clicked.connect(lambda: self.seek_delta_requested.emit(15.0))
        btn_row.addWidget(fw15)

        btn_row.addStretch()

        # Speed
        spd_lbl = QLabel("Speed:")
        spd_lbl.setStyleSheet("color: #475569; font-size: 10px;")
        btn_row.addWidget(spd_lbl)

        self._speed_btns: dict[float, QPushButton] = {}
        for spd in (0.5, 1.0, 2.0, 4.0):
            b = _btn(f"{spd:g}×", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
            b.setFixedWidth(42)
            b.clicked.connect(lambda _checked, s=spd: self._on_speed_clicked(s))
            btn_row.addWidget(b)
            self._speed_btns[spd] = b

        # Step one frame (useful when paused)
        btn_row.addSpacing(8)
        self._step_btn = _btn("▷1", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        self._step_btn.setFixedWidth(42)
        self._step_btn.setToolTip("Step one frame (only active when paused)")
        self._step_btn.setEnabled(False)
        self._step_btn.clicked.connect(lambda: self.step_frame_requested.emit())
        btn_row.addWidget(self._step_btn)

        ctrl.addLayout(btn_row)
        layout.addWidget(self._controls)

        # Highlight 1× as default active speed
        self._active_speed: float = 1.0
        self._highlight_speed(1.0)

        self._controls.setVisible(is_video)
        self._duration_ms: float = 0.0

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_released(self):
        self._slider_dragging = False
        if self._duration_ms > 0:
            frac = self._slider.value() / 10000.0
            self.seek_to_ms_requested.emit(frac * self._duration_ms)

    def _on_speed_clicked(self, speed: float):
        self._highlight_speed(speed)
        self.speed_requested.emit(speed)

    def _highlight_speed(self, speed: float):
        self._active_speed = speed
        for s, b in self._speed_btns.items():
            active = abs(s - speed) < 0.01
            b.setStyleSheet(f"""
                QPushButton {{
                    background-color: {'#7c3aed' if active else '#1e293b'};
                    color: {'#ffffff' if active else '#94a3b8'};
                    border: 1px solid {'#7c3aed' if active else '#334155'};
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 5px 12px;
                }}
                QPushButton:hover {{
                    background-color: {'#6d28d9' if active else '#334155'};
                }}
            """)

    @staticmethod
    def _fmt_ms(ms: float) -> str:
        s = int(ms / 1000)
        return f"{s // 60}:{s % 60:02d}"

    # ── Public API ────────────────────────────────────────────────────────────

    def update_frame(self, frame_bgr):
        import numpy as np
        frame_bgr = np.ascontiguousarray(frame_bgr)
        h, w = frame_bgr.shape[:2]
        rgb = frame_bgr[:, :, ::-1].copy()
        img = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img)
        self._label.setPixmap(
            pix.scaled(self._label.size(),
                       Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        )

    def update_video_state(self, pos_ms: float, duration_ms: float, speed: float, paused: bool = False):
        """Called from the poll timer (Qt main thread) to update the controls bar."""
        self._duration_ms = duration_ms
        if not self._slider_dragging and duration_ms > 0:
            self._slider.setValue(int(pos_ms / duration_ms * 10000))
        self._time_lbl.setText(f"{self._fmt_ms(pos_ms)} / {self._fmt_ms(duration_ms)}")
        if abs(speed - self._active_speed) > 0.01:
            self._highlight_speed(speed)
        # Update pause button label and step button state
        self._play_btn.setText("▶" if paused else "⏸")
        self._play_btn.setToolTip("Play" if paused else "Pause")
        self._step_btn.setEnabled(paused)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


# ── Single service row ─────────────────────────────────────────────────────────

class ServiceRow(QFrame):
    _state_changed = pyqtSignal()
    _duplicate_requested = pyqtSignal(object)  # emits the new ServiceConfig to the parent dialog

    def __init__(self, cfg: ServiceConfig, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._registry = get_registry()
        self._spinner_idx = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._spin)
        self._state_changed.connect(self._refresh)
        self._preview_dialog: PreviewDialog | None = None
        self._preview_poll_timer = QTimer(self)
        self._preview_poll_timer.timeout.connect(self._poll_preview)
        self.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 10)
        outer.setSpacing(6)

        # ── Top row ────────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(10)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #475569; font-size: 16px;")
        self._dot.setFixedWidth(20)
        top.addWidget(self._dot)

        name_lbl = QLabel(self._cfg.name)
        name_lbl.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: bold;")
        name_lbl.setFixedWidth(160)
        top.addWidget(name_lbl)

        self._ports_lbl = QLabel()
        self._ports_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        self._ports_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._update_ports_label()
        top.addWidget(self._ports_lbl, stretch=1)

        self._status_lbl = QLabel("Stopped")
        self._status_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._status_lbl.setFixedWidth(72)
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._status_lbl)

        self._start_btn = _btn("▶  Start", "#7c3aed", "#6d28d9")
        self._start_btn.setFixedWidth(82)
        self._start_btn.clicked.connect(self._start)
        top.addWidget(self._start_btn)

        self._stop_btn = _btn("■  Stop", "#dc2626", "#b91c1c")
        self._stop_btn.setFixedWidth(76)
        self._stop_btn.clicked.connect(self._stop)
        top.addWidget(self._stop_btn)

        self._record_btn = _btn("●  Rec", "#7f1d1d", "#991b1b", "#fecaca", border_color="#7f1d1d")
        self._record_btn.setFixedWidth(84)
        self._record_btn.clicked.connect(self._toggle_recording)
        top.addWidget(self._record_btn)

        self._preview_btn = _btn("👁  Preview", "#1e3a5f", "#1e4a7f", "#60a5fa", border_color="#1e4a7f")
        self._preview_btn.setFixedWidth(90)
        self._preview_btn.clicked.connect(self._toggle_preview)
        top.addWidget(self._preview_btn)

        self._debug_btn = _btn("⏺  Debug", "#1a2e1a", "#1f3d1f", "#86efac", border_color="#1f3d1f")
        self._debug_btn.setFixedWidth(84)
        self._debug_btn.clicked.connect(self._toggle_direction_debug)
        top.addWidget(self._debug_btn)

        self._more_btn = QPushButton("⋯")
        self._more_btn.setFixedWidth(34)
        self._more_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 15px;
                font-weight: bold;
                padding: 3px 0;
            }
            QPushButton:hover { background-color: #334155; color: #e2e8f0; }
            QPushButton::menu-indicator { width: 0; }
        """)
        more_menu = QMenu(self._more_btn)
        more_menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item { padding: 7px 18px; border-radius: 4px; font-size: 12px; }
            QMenu::item:selected { background-color: #7c3aed; }
            QMenu::separator { height: 1px; background: #334155; margin: 3px 8px; }
        """)
        self._act_relaunch = more_menu.addAction("↺  Relaunch")
        self._act_relaunch.triggered.connect(self._relaunch)
        self._act_edit = more_menu.addAction("✎  Edit config")
        self._act_edit.triggered.connect(self._edit)
        self._act_duplicate = more_menu.addAction("⧉  Duplicate")
        self._act_duplicate.triggered.connect(self._duplicate)
        more_menu.addSeparator()
        self._act_remove = more_menu.addAction("✕  Remove")
        self._act_remove.triggered.connect(self._remove)
        self._more_btn.setMenu(more_menu)
        top.addWidget(self._more_btn)

        outer.addLayout(top)

        # ── Request log (collapsible) ──────────────────────────────────────
        log_toggle_row = QHBoxLayout()
        self._log_toggle = QPushButton("▶  Detection log")
        self._log_toggle.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: #334155; font-size: 10px;
                text-align: left; padding: 0; padding-left: 24px;
            }
            QPushButton:hover { color: #64748b; }
        """)
        self._log_toggle.setCheckable(True)
        self._log_toggle.setChecked(False)
        self._log_toggle.clicked.connect(self._toggle_log)
        log_toggle_row.addWidget(self._log_toggle)
        log_toggle_row.addStretch()
        outer.addLayout(log_toggle_row)

        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFixedHeight(110)
        self._log_box.setVisible(False)
        outer.addWidget(self._log_box)

    def _toggle_log(self, checked: bool):
        self._log_box.setVisible(checked)
        self._log_toggle.setText("▼  Detection log" if checked else "▶  Detection log")
        if checked:
            self._update_log_box()

    def _update_log_box(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc is None:
            return
        entries = svc.get_log_entries()
        if not entries:
            return
        lines = [str(e) for e in reversed(entries)]
        self._log_box.setPlainText("\n".join(lines))
        self._log_box.verticalScrollBar().setValue(0)

    def _update_ports_label(self):
        model_name = self._cfg.model_path.split("/")[-1].split("\\")[-1] if self._cfg.model_path else "no model"
        auto = "  ⟳" if self._cfg.auto_start else ""
        rec = "  🎥" if self._cfg.record_stream else ""
        mode = self._cfg.input_mode if self._cfg.input_mode in ("http", "rtsp", "video") else (
            "rtsp" if self._cfg.rtsp_enabled else "http"
        )
        if mode == "rtsp":
            source = f"rtsp://{self._cfg.rtsp_ip}:{self._cfg.rtsp_port}/…"
            self._ports_lbl.setText(
                f"📷 {source}  →  {self._cfg.output_host}:{self._cfg.output_port}"
                f"   [{model_name}]{auto}{rec}"
            )
        elif mode == "video":
            video_name = self._cfg.video_path.split("/")[-1].split("\\")[-1] if self._cfg.video_path else "video"
            loop = "  ↻" if self._cfg.video_loop else ""
            self._ports_lbl.setText(
                f"🎬 {video_name}  →  {self._cfg.output_host}:{self._cfg.output_port}"
                f"   [{model_name}]{auto}{rec}{loop}"
            )
        else:
            self._ports_lbl.setText(
                f":{self._cfg.input_port}  →  {self._cfg.output_host}:{self._cfg.output_port}"
                f"   [{model_name}]{auto}"
            )

    def config(self) -> ServiceConfig:
        return self._cfg

    def refresh(self):
        self._refresh()
        if self._log_box.isVisible():
            self._update_log_box()

    def _refresh(self):
        state = self._registry.get_state(self._cfg.name)

        loading = state == STATE_LOADING
        running = state == STATE_RUNNING
        error   = state == STATE_ERROR

        self._start_btn.setEnabled(state in (STATE_STOPPED, STATE_ERROR))
        self._stop_btn.setEnabled(running or loading)
        self._act_relaunch.setEnabled(state != STATE_LOADING)
        self._act_edit.setEnabled(state in (STATE_STOPPED, STATE_ERROR))

        mode = self._cfg.input_mode if self._cfg.input_mode in ("http", "rtsp", "video") else (
            "rtsp" if self._cfg.rtsp_enabled else "http"
        )
        can_record = mode in ("rtsp", "video")
        svc = self._registry.get_service(self._cfg.name)
        is_recording = svc.is_recording if svc else (self._cfg.record_stream and can_record)
        is_previewing = svc.is_previewing if svc else False
        is_debugging = svc.is_direction_debugging if svc else False
        self._record_btn.setVisible(can_record)
        self._record_btn.setEnabled(running and can_record)
        self._record_btn.setText("■  Rec Off" if is_recording else "●  Rec")
        self._preview_btn.setVisible(can_record)
        self._preview_btn.setEnabled(running and can_record)
        self._preview_btn.setText("■  Preview" if is_previewing else "👁  Preview")
        self._debug_btn.setVisible(can_record)
        self._debug_btn.setEnabled(running and can_record)
        self._debug_btn.setText("■  Debug" if is_debugging else "⏺  Debug")

        if running:
            self._dot.setStyleSheet("color: #4ade80; font-size: 16px;")
            self._status_lbl.setText("Running")
            self._status_lbl.setStyleSheet("color: #4ade80; font-size: 11px;")
            self._spinner_timer.stop()
        elif loading:
            self._dot.setStyleSheet("color: #fbbf24; font-size: 16px;")
            self._status_lbl.setStyleSheet("color: #fbbf24; font-size: 11px;")
            if not self._spinner_timer.isActive():
                self._spinner_timer.start(80)
        elif error:
            self._dot.setStyleSheet("color: #f87171; font-size: 16px;")
            self._status_lbl.setText("Error")
            self._status_lbl.setStyleSheet("color: #f87171; font-size: 11px;")
            self._spinner_timer.stop()
        else:
            self._dot.setStyleSheet("color: #475569; font-size: 16px;")
            self._status_lbl.setText("Stopped")
            self._status_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
            self._spinner_timer.stop()

    def _spin(self):
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_FRAMES)
        self._status_lbl.setText(f"{_SPINNER_FRAMES[self._spinner_idx]} Loading")

    def _on_start_done(self, error: str):
        self._state_changed.emit()
        if error:
            QTimer.singleShot(0, lambda: self._show_start_error(error))

    def _show_start_error(self, error: str):
        svc = self._registry.get_service(self._cfg.name)
        err_detail = error
        if svc and svc.error_msg:
            err_detail = svc.error_msg
        QMessageBox.critical(self.window(), f"Failed to start '{self._cfg.name}'", err_detail)

    def _start(self):
        error = self._registry.start_async(self._cfg.name, self._on_start_done)
        if error:
            QMessageBox.critical(self.window(), "Cannot Start", error)
            return
        self._refresh()

    def _stop(self):
        self._registry.stop(self._cfg.name)
        self._spinner_timer.stop()
        self._stop_preview_ui()
        self._refresh()

    def _toggle_recording(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc is None:
            QMessageBox.warning(self.window(), "Recording", "Service is not available.")
            return
        if not svc.is_running:
            QMessageBox.warning(self.window(), "Recording", "Start the service before recording.")
            return

        if svc.is_recording:
            svc.stop_recording()
        else:
            err = svc.start_recording(record_dir=self._cfg.record_dir)
            if err:
                QMessageBox.warning(self.window(), "Recording", err)
                return
        self._refresh()

    def _toggle_direction_debug(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc is None:
            return
        if not svc.is_running:
            QMessageBox.warning(self.window(), "Direction Debug", "Start the service first.")
            return
        if svc.is_direction_debugging:
            path = svc.stop_direction_debug()
            QMessageBox.information(
                self.window(), "Direction Debug",
                f"Debug log saved to:\n{path}"
            )
        else:
            import os
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.expanduser("~/VisionQ_debug")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"direction_{self._cfg.name}_{ts}.csv")
            svc.start_direction_debug(path)
            QMessageBox.information(
                self.window(), "Direction Debug",
                f"Capturing to:\n{path}\n\nClick Debug again to stop."
            )
        self._refresh()

    def _toggle_preview(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc is None:
            return
        if svc.is_previewing:
            self._stop_preview_ui()
        else:
            err = svc.start_preview()
            if err:
                QMessageBox.warning(self.window(), "Preview", err)
                return
            if self._preview_dialog is None:
                mode = self._cfg.input_mode if self._cfg.input_mode in ("http", "rtsp", "video") else (
                    "rtsp" if self._cfg.rtsp_enabled else "http"
                )
                self._preview_dialog = PreviewDialog(
                    self._cfg.name,
                    is_video=(mode == "video"),
                    parent=self.window(),
                )
                self._preview_dialog.closed.connect(self._on_preview_dialog_closed)
                self._preview_dialog.seek_delta_requested.connect(self._on_preview_seek_delta)
                self._preview_dialog.seek_to_ms_requested.connect(self._on_preview_seek_to_ms)
                self._preview_dialog.speed_requested.connect(self._on_preview_speed)
                self._preview_dialog.pause_toggled.connect(self._on_preview_pause_toggled)
                self._preview_dialog.step_frame_requested.connect(self._on_preview_step_frame)
            self._preview_dialog.show()
            self._preview_dialog.raise_()
            self._preview_poll_timer.start(50)  # poll at 20 fps
            self._refresh()

    def _stop_preview_ui(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc:
            svc.stop_preview()
        self._preview_poll_timer.stop()
        if self._preview_dialog:
            self._preview_dialog.hide()
        self._refresh()

    def _on_preview_dialog_closed(self):
        """Called when the user clicks X on the preview window."""
        self._stop_preview_ui()

    def _on_preview_seek_delta(self, delta: float):
        svc = self._registry.get_service(self._cfg.name)
        if svc:
            svc.seek_video_relative(delta)

    def _on_preview_seek_to_ms(self, target_ms: float):
        svc = self._registry.get_service(self._cfg.name)
        if svc:
            svc.seek_video_to_ms(target_ms)

    def _on_preview_speed(self, speed: float):
        svc = self._registry.get_service(self._cfg.name)
        if svc:
            svc.set_video_speed(speed)

    def _on_preview_pause_toggled(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc:
            svc.toggle_video_pause()

    def _on_preview_step_frame(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc:
            svc.step_video_frame()

    def _poll_preview(self):
        """Called by QTimer on the main thread — fetch latest frame and render."""
        svc = self._registry.get_service(self._cfg.name)
        if svc is None or not svc.is_previewing:
            self._preview_poll_timer.stop()
            self._refresh()
            return
        frame = svc.get_preview_frame()
        if frame is not None and self._preview_dialog:
            self._preview_dialog.update_frame(frame)
        # Update progress slider/time label for video mode
        mode = self._cfg.input_mode if self._cfg.input_mode in ("http", "rtsp", "video") else (
            "rtsp" if self._cfg.rtsp_enabled else "http"
        )
        if mode == "video" and self._preview_dialog:
            pos_ms, dur_ms, speed, paused = svc.get_video_state()
            self._preview_dialog.update_video_state(pos_ms, dur_ms, speed, paused)

    def _relaunch(self):
        cfg = self._registry.get_config(self._cfg.name) or self._cfg
        dlg = ServiceConfigDialog(cfg, parent=self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_cfg = dlg.result_config
        if new_cfg is None:
            return
        self._registry.upsert_config(new_cfg)
        self._cfg = new_cfg
        self._update_ports_label()

        error = self._registry.restart_async(new_cfg.name, self._on_start_done)
        if error:
            QMessageBox.critical(self.window(), "Cannot Relaunch", error)
            return
        self._refresh()

    def _edit(self):
        dlg = ServiceConfigDialog(self._cfg, parent=self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_cfg = dlg.result_config
        if new_cfg is None:
            return
        self._registry.upsert_config(new_cfg)
        self._cfg = new_cfg
        self._update_ports_label()

    def _duplicate(self):
        import dataclasses
        # Pre-fill with a "_copy" name so the user can rename before saving
        copy_cfg = dataclasses.replace(self._cfg, name=f"{self._cfg.name}_copy")
        dlg = ServiceConfigDialog(copy_cfg, parent=self.window(), is_duplicate=True)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_cfg = dlg.result_config
        if new_cfg is None:
            return
        self._duplicate_requested.emit(new_cfg)

    def cleanup(self):
        """Stop all timers and close the preview dialog. Call before destroying the row."""
        self._spinner_timer.stop()
        self._preview_poll_timer.stop()
        if self._preview_dialog is not None:
            for sig in (
                self._preview_dialog.closed,
                self._preview_dialog.seek_delta_requested,
                self._preview_dialog.seek_to_ms_requested,
                self._preview_dialog.speed_requested,
                self._preview_dialog.pause_toggled,
                self._preview_dialog.step_frame_requested,
            ):
                try:
                    sig.disconnect()
                except Exception:
                    pass
            self._preview_dialog.close()
            self._preview_dialog = None
        svc = self._registry.get_service(self._cfg.name)
        if svc:
            svc.stop_preview()

    def _remove(self):
        state = self._registry.get_state(self._cfg.name)
        msg = f"Remove service '{self._cfg.name}'?"
        if state in (STATE_RUNNING, STATE_LOADING):
            msg += "\nIt is currently active and will be stopped."
        reply = QMessageBox.question(
            self.window(), "Remove Service", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.cleanup()
        self._registry.remove_config(self._cfg.name)
        self.setParent(None)   # type: ignore
        self.deleteLater()


# ── Main dialog ────────────────────────────────────────────────────────────────

_RECV_HOST = "127.0.0.1"
_RECV_PORT = 6060


class DetectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Service Manager")
        self.setMinimumWidth(860)
        self.setMinimumHeight(480)
        self.setStyleSheet(_BASE)
        self._rows: list[ServiceRow] = []
        self._build_ui()
        self._load_existing()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start(1000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 16)

        hdr = QHBoxLayout()
        title = QLabel("⚡  Service Manager")
        title.setStyleSheet("color: #a78bfa; font-size: 16px; font-weight: bold;")
        hdr.addWidget(title)
        hdr.addStretch()
        add_btn = _btn("＋  Add Service", "#064e3b", "#065f46", "#34d399", border_color="#065f46")
        add_btn.clicked.connect(self._add_service)
        hdr.addWidget(add_btn)
        layout.addLayout(hdr)

        sub = QLabel(
            "Each service runs YOLO detection and pushes JSON results to the configured output.  "
            "Input can be an HTTP endpoint, a live RTSP camera stream, or a looping local video file.  "
            "Services marked ⟳ auto-start when VisionQ opens."
        )
        sub.setStyleSheet("color: #475569; font-size: 11px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        col_hdr = QWidget()
        col_hdr.setStyleSheet("background: transparent;")
        col_row = QHBoxLayout(col_hdr)
        col_row.setContentsMargins(46, 0, 14, 0)
        col_row.setSpacing(0)

        def _col(text, width=None):
            l = QLabel(text)
            l.setStyleSheet("color: #334155; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
            if width:
                l.setFixedWidth(width)
            return l

        col_row.addWidget(_col("NAME", 160))
        col_row.addWidget(_col("SOURCE  →  OUTPUT   [MODEL]"), 1)
        col_row.addWidget(_col("STATUS", 80))
        layout.addWidget(col_hdr)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setSpacing(8)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.addStretch()
        self._scroll.setWidget(self._rows_container)
        layout.addWidget(self._scroll, stretch=1)

        self._empty_lbl = QLabel(
            "No services configured yet.\nClick  ＋ Add Service  to create one."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #334155; font-size: 13px; line-height: 1.8;")
        layout.addWidget(self._empty_lbl)

        # ── Result receiver bar ────────────────────────────────────────────
        recv_bar = QFrame()
        recv_bar.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
        """)
        recv_layout = QHBoxLayout(recv_bar)
        recv_layout.setContentsMargins(12, 8, 12, 8)
        recv_layout.setSpacing(10)

        recv_icon = QLabel("📡")
        recv_icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        recv_layout.addWidget(recv_icon)

        self._recv_status = QLabel(f"Result receiver — http://{_RECV_HOST}:{_RECV_PORT}")
        self._recv_status.setStyleSheet("color: #475569; font-size: 11px; background: transparent; border: none;")
        recv_layout.addWidget(self._recv_status)
        recv_layout.addStretch()

        self._recv_start_btn = _btn("▶  Start receiver", "#064e3b", "#065f46", "#34d399", border_color="#065f46")
        self._recv_start_btn.clicked.connect(self._start_receiver)
        recv_layout.addWidget(self._recv_start_btn)

        self._recv_stop_btn = _btn("■  Stop", "#dc2626", "#b91c1c")
        self._recv_stop_btn.clicked.connect(self._stop_receiver)
        recv_layout.addWidget(self._recv_stop_btn)

        self._recv_open_btn = _btn("🌐  Open in browser", "#1e3a5f", "#1e4a7f", "#60a5fa", border_color="#1e4a7f")
        self._recv_open_btn.clicked.connect(self._open_browser)
        recv_layout.addWidget(self._recv_open_btn)

        layout.addWidget(recv_bar)
        self._refresh_receiver()

        foot = QHBoxLayout()
        foot.addStretch()
        close_btn = _btn("Close", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        layout.addLayout(foot)

    def _load_existing(self):
        for cfg in get_registry().get_configs():
            self._add_row(cfg)
        self._update_empty()

    def _add_row(self, cfg: ServiceConfig):
        row = ServiceRow(cfg)
        row._duplicate_requested.connect(self._on_duplicate_requested)
        self._rows.append(row)
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        self._update_empty()

    def _on_duplicate_requested(self, new_cfg: ServiceConfig):
        existing = [r.config().name for r in self._rows if r.parent() is not None]
        if new_cfg.name in existing:
            QMessageBox.warning(self, "Duplicate Name",
                                f"A service named '{new_cfg.name}' already exists.")
            return
        get_registry().upsert_config(new_cfg)
        self._add_row(new_cfg)
        # Don't auto-start — user decides when to start the duplicate

    def _update_empty(self):
        alive = []
        for r in self._rows:
            try:
                if r.parent() is not None:
                    alive.append(r)
            except RuntimeError:
                pass
        self._rows = alive
        has_rows = bool(self._rows)
        self._empty_lbl.setVisible(not has_rows)
        self._scroll.setVisible(has_rows)

    def _add_service(self):
        dlg = ServiceConfigDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cfg = dlg.result_config
        if cfg is None:
            return
        existing = [r.config().name for r in self._rows if r.parent() is not None]
        if cfg.name in existing:
            QMessageBox.warning(self, "Duplicate Name",
                                f"A service named '{cfg.name}' already exists.")
            return
        get_registry().upsert_config(cfg)
        self._add_row(cfg)
        self._rows[-1]._start()

    def _refresh_receiver(self):
        running = get_receiver().is_running
        self._recv_start_btn.setVisible(not running)
        self._recv_stop_btn.setVisible(running)
        self._recv_open_btn.setEnabled(running)
        if running:
            self._recv_status.setText(
                f"Result receiver running — http://{_RECV_HOST}:{_RECV_PORT}"
            )
            self._recv_status.setStyleSheet("color: #4ade80; font-size: 11px; background: transparent; border: none;")
        else:
            self._recv_status.setText(
                f"Result receiver stopped — http://{_RECV_HOST}:{_RECV_PORT}"
            )
            self._recv_status.setStyleSheet("color: #475569; font-size: 11px; background: transparent; border: none;")

    def _start_receiver(self):
        err = get_receiver().start(host=_RECV_HOST, port=_RECV_PORT)
        if err:
            QMessageBox.critical(self, "Result Receiver Error", err)
        else:
            self._refresh_receiver()
            self._open_browser()

    def _stop_receiver(self):
        get_receiver().stop()
        self._refresh_receiver()

    def _open_browser(self):
        webbrowser.open(f"http://{_RECV_HOST}:{_RECV_PORT}")

    def _refresh_all(self):
        self._update_empty()
        for row in self._rows:
            if row.parent() is not None:
                row.refresh()

    def closeEvent(self, event):
        self._timer.stop()
        for row in self._rows:
            try:
                if row.parent() is not None:
                    row.cleanup()
            except Exception:
                pass
        super().closeEvent(event)
