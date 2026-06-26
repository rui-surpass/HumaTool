import sys
from PyQt6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QGridLayout, QLabel, 
    QComboBox, QSlider, QCheckBox, QPushButton, QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap, QColor

class TeleopStreamWidget(QGroupBox):
    """
    Widget for controlling VisionProTeleop Stream.
    """
    # Signals
    start_stream_requested = pyqtSignal()
    stop_stream_requested = pyqtSignal()
    restart_stream_requested = pyqtSignal(str, int, int, bool, str) # res, fps, bitrate, stereo, latency
    mirror_toggled = pyqtSignal(bool)
    rotate_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__("VisionProTeleop Stream", parent)
        self.is_streaming = False
        self.fps_map = {"2560": 60, "3840": 30, "4416": 15}
        self.default_bitrate_kbps = 12000
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout()
        self.setLayout(layout)

        # --- Controls ---
        # Start/Stop Button
        self.btn_stream = QPushButton("Start Streaming")
        self.btn_stream.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 5px;")
        self.btn_stream.clicked.connect(self.on_stream_clicked)
        layout.addWidget(self.btn_stream, 0, 0, 1, 3)

        # Config Row 1
        layout.addWidget(QLabel("Resolution:"), 1, 0)
        self.combo_res = QComboBox()
        self.combo_res.addItems(["2560x720 (Stereo 720p)", "3840x1080 (Stereo 1080p)", "4416x1242 (Stereo 2K)"])
        self.combo_res.setToolTip("Stream Resolution. Default: 3840x1080 (30fps).")
        self.combo_res.setCurrentIndex(1) # Default 3840x1080
        self.combo_res.currentIndexChanged.connect(self.on_config_change_attempt)
        layout.addWidget(self.combo_res, 1, 1, 1, 2)

        self.combo_res.currentIndexChanged.connect(self.on_resolution_changed_ui) # New handler
        layout.addWidget(self.combo_res, 1, 1, 1, 2)

        # Video Format
        layout.addWidget(QLabel("Format:"), 2, 0)
        self.combo_format = QComboBox()
        self.combo_format.addItems(["Stereo (SBS) Default", "Mono"])
        self.combo_format.setToolTip("Stereo requires ZED-M side-by-side mode.")
        self.combo_format.currentIndexChanged.connect(self.on_config_change_attempt)
        layout.addWidget(self.combo_format, 2, 1, 1, 2)

        # Bitrate
        layout.addWidget(QLabel("Bitrate (Kbps):"), 3, 0)
        self.slider_bitrate = QSlider(Qt.Orientation.Horizontal)
        self.slider_bitrate.setRange(2000, 50000) # 2Mbps - 50Mbps
        self.slider_bitrate.setValue(self.default_bitrate_kbps)
        self.slider_bitrate.setSingleStep(128)
        self.label_bitrate = QLabel(f"{self.default_bitrate_kbps} Kbps")
        self.slider_bitrate.valueChanged.connect(lambda v: self.label_bitrate.setText(f"{v} Kbps"))
        # Bitrate can be changed dynamically (if we implement it) or requires restart.
        # Impl plan says restart.
        self.slider_bitrate.sliderReleased.connect(self.on_config_change_attempt) 
        layout.addWidget(self.slider_bitrate, 2, 1)
        layout.addWidget(self.label_bitrate, 2, 2)

        # Latency Mode
        layout.addWidget(QLabel("Latency:"), 3, 0)
        self.combo_latency = QComboBox()
        self.combo_latency.addItems(["Low Latency", "Balanced", "High Quality"])
        layout.addWidget(self.combo_latency, 3, 1, 1, 2)

        # Defaults
        self.btn_default = QPushButton("Reset Defaults")
        self.btn_default.clicked.connect(self.reset_defaults)
        layout.addWidget(self.btn_default, 3, 2)

        # --- Display Options ---
        layout.addWidget(QLabel("Display:"), 4, 0)
        hbox_display = QHBoxLayout()
        self.chk_mirror = QCheckBox("Mirror")
        self.chk_mirror.toggled.connect(self.mirror_toggled.emit)
        
        self.chk_rotate = QCheckBox("Rotate 180")
        self.chk_rotate.toggled.connect(self.rotate_toggled.emit)
        
        hbox_display.addWidget(self.chk_mirror)
        hbox_display.addWidget(self.chk_rotate)
        layout.addLayout(hbox_display, 4, 1, 1, 2)

        # --- Preview & Status ---
        self.label_preview = QLabel("NO SIGNAL")
        self.label_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_preview.setStyleSheet("background-color: black; color: white; border: 1px solid #555;")
        self.label_preview.setMinimumSize(320, 180) # 16:9 aspect
        layout.addWidget(self.label_preview, 5, 0, 1, 3)

        self.label_status = QLabel("Resolution: - | Bitrate: - | Latency: - | Loss: 0%")
        self.label_status.setStyleSheet("font-weight: bold; color: gray;")
        layout.addWidget(self.label_status, 6, 0, 1, 3)

        # Set styling
        self.setStyleSheet("""
            QGroupBox {
                border: 1px solid #4CAF50;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: #4CAF50;
            }
        """)

    def on_stream_clicked(self):
        if not self.is_streaming:
            # Request Start
            self.start_stream_requested.emit()
        else:
            # Request Stop
            self.stop_stream_requested.emit()

    def set_streaming_state(self, streaming):
        self.is_streaming = streaming
        if streaming:
            self.btn_stream.setText("Stop Streaming")
            self.btn_stream.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 5px;")
            self.label_status.setStyleSheet("font-weight: bold; color: #2ecc71;") # Green
        else:
            self.btn_stream.setText("Start Streaming")
            self.btn_stream.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 5px;")
            self.label_status.setStyleSheet("font-weight: bold; color: gray;")
            self.label_preview.setText("NO SIGNAL")

    def config_matches_current(self, res_text, bitrate):
        """Check if UI matches current running config."""
        # This is a simplification. Ideally controller keeps track.
        # We assume if streaming, any change is a mismatch.
        return not self.is_streaming 

    def on_config_change_attempt(self):
        if self.is_streaming:
            reply = QMessageBox.question(
                self, "Restart Required", 
                "Changing parameters requires restarting the stream. Do you want to restart now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.request_restart()
            else:
                # Revert UI? Slightly complex without stored state.
                # Ideally we just don't apply it until restart.
                pass

    def on_resolution_changed_ui(self, index):
        """Auto-configure Format based on Resolution."""
        text = self.combo_res.currentText()
        if "Stereo" in text or "2560" in text or "3840" in text:
            # Force Stereo
            idx = self.combo_format.findText("Stereo (SBS) Default")
            if idx >= 0: self.combo_format.setCurrentIndex(idx)
        
        # Determine if restart needed
        self.on_config_change_attempt()

    # Updated Signal
    restart_stream_requested = pyqtSignal(str, int, int, bool, str) # res, fps, bitrate, stereo, latency

    # ... (skipping init_ui updates as they are done in previous step) ...

    def request_restart(self):
        res_str = self.combo_res.currentText().split(' ')[0]
        # Auto-FPS from Map
        width = res_str.split('x')[0]
        fps = self.fps_map.get(width, 30)
            
        bitrate = self.slider_bitrate.value()
        stereo = "Stereo" in self.combo_format.currentText()
        latency = self.combo_latency.currentText()
        
        self.restart_stream_requested.emit(res_str, fps, bitrate, stereo, latency)
    
    def get_config(self):
        res_str = self.combo_res.currentText().split(' ')[0]
        width = res_str.split('x')[0]
        fps = self.fps_map.get(width, 30)
        
        stereo = "Stereo" in self.combo_format.currentText()
        latency = self.combo_latency.currentText()
        return res_str, fps, self.slider_bitrate.value(), stereo, latency

    def reset_defaults(self):
        self.combo_res.setCurrentIndex(1) # 3840x1080
        self.slider_bitrate.setValue(self.default_bitrate_kbps)
        self.combo_latency.setCurrentIndex(0)

    def update_frame(self, cv_image):
        """Update preview with opencv image (BGR)."""
        if cv_image is None: return
        
        # Resize to fit label
        h, w, ch = cv_image.shape
        bytes_per_line = ch * w
        
        # Convert BGR to RGB for Qt
        # Note: Inefficient for high FPS, but fine for preview
        rgb_image = cv_image[:, :, [2, 1, 0]].copy() 
        
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        
        # Scale to label
        scaled = pixmap.scaled(self.label_preview.size(), Qt.AspectRatioMode.KeepAspectRatio)
        self.label_preview.setPixmap(scaled)

    def update_stats(self, res, bitrate, latency, loss):
        """Update status label."""
        loss_color = "red" if loss > 5.0 else "green"
        self.label_status.setText(
            f"Resolution: {res} | Bitrate: {bitrate} Kbps | Latency: {latency:.1f} ms | "
            f"Loss: <font color='{loss_color}'>{loss:.1f}%</font>"
        )
