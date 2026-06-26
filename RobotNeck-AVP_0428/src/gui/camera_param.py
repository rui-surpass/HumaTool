from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from src.gui.camera_panel_logic import (
    build_camera_panel_state,
    build_rtp_stream_ui_state,
)


class CameraParamWidget(QGroupBox):
    """
    Widget for adjusting ZED-M camera parameters and monitoring ZED SDK state.
    """

    param_changed = pyqtSignal(str, float)
    auto_exposure_toggled = pyqtSignal(bool)
    auto_wb_toggled = pyqtSignal(bool)
    confidence_changed = pyqtSignal(int)
    disparity_changed = pyqtSignal(int)
    capture_mode_changed = pyqtSignal(str)
    focus_changed = pyqtSignal(int)
    auto_focus_toggled = pyqtSignal(bool)
    rtp_stream_requested = pyqtSignal(bool, str, int, int)
    camera_connection_requested = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__("ZED-M Camera Parameters", parent)
        self.connected = False
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout()
        self.setLayout(root_layout)

        grp_controls = QGroupBox("Camera Controls")
        controls_layout = QGridLayout()
        grp_controls.setLayout(controls_layout)

        controls_layout.addWidget(QLabel("Camera Settings (Synced with Stream):"), 0, 0, 1, 3)
        self.btn_camera_connection = QPushButton("Connect Camera")
        self.btn_camera_connection.clicked.connect(self.on_camera_connection_clicked)
        controls_layout.addWidget(self.btn_camera_connection, 1, 0, 1, 3)
        self.label_res_info = QLabel("Resolution: Auto")
        self.label_fps_info = QLabel("FPS: Auto")
        controls_layout.addWidget(self.label_res_info, 2, 0, 1, 2)
        controls_layout.addWidget(self.label_fps_info, 2, 2)

        controls_layout.addWidget(QLabel("Capture Mode:"), 3, 0)
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Stereo (SBS)", "Left Eye", "Right Eye"])
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        controls_layout.addWidget(self.combo_mode, 3, 1, 1, 2)

        self.chk_auto_focus = QCheckBox("Auto Focus")
        self.chk_auto_focus.setChecked(False)
        self.chk_auto_focus.toggled.connect(self.on_auto_focus_toggled)
        controls_layout.addWidget(self.chk_auto_focus, 4, 0)

        self.slider_focus = QSlider(Qt.Orientation.Horizontal)
        self.slider_focus.setRange(0, 100)
        self.slider_focus.setValue(65)
        self.label_focus = QLabel("65")
        self.slider_focus.valueChanged.connect(lambda v: self.label_focus.setText(str(v)))
        self.slider_focus.valueChanged.connect(lambda v: self.focus_changed.emit(v))
        controls_layout.addWidget(self.slider_focus, 4, 1)
        controls_layout.addWidget(self.label_focus, 4, 2)
        
        row = 5
        self.chk_auto_exposure = QCheckBox("Auto Exposure")
        self.chk_auto_exposure.setChecked(True)
        self.chk_auto_exposure.toggled.connect(self.on_auto_exposure_toggled)
        controls_layout.addWidget(self.chk_auto_exposure, row, 0)

        self.slider_exposure = QSlider(Qt.Orientation.Horizontal)
        self.slider_exposure.setRange(0, 100)
        self.slider_exposure.setEnabled(False)
        self.label_exposure = QLabel("50%")
        self.slider_exposure.valueChanged.connect(lambda v: self.label_exposure.setText(f"{v}%"))
        self.slider_exposure.valueChanged.connect(lambda v: self.param_changed.emit("EXPOSURE", v))
        controls_layout.addWidget(self.slider_exposure, row, 1)
        controls_layout.addWidget(self.label_exposure, row, 2)
        row += 1

        self.chk_auto_wb = QCheckBox("Auto WB")
        self.chk_auto_wb.setChecked(True)
        self.chk_auto_wb.toggled.connect(self.on_auto_wb_toggled)
        controls_layout.addWidget(self.chk_auto_wb, row, 0)

        self.slider_wb = QSlider(Qt.Orientation.Horizontal)
        self.slider_wb.setRange(2800, 10000)
        self.slider_wb.setSingleStep(100)
        self.slider_wb.setValue(4600)
        self.slider_wb.setEnabled(False)
        self.label_wb = QLabel("4600 K")
        self.slider_wb.valueChanged.connect(lambda v: self.label_wb.setText(f"{v} K"))
        self.slider_wb.valueChanged.connect(lambda v: self.param_changed.emit("WHITEBALANCE", v))
        controls_layout.addWidget(self.slider_wb, row, 1)
        controls_layout.addWidget(self.label_wb, row, 2)
        row += 1

        controls_layout.addWidget(QLabel("Gain:"), row, 0)
        self.slider_gain = QSlider(Qt.Orientation.Horizontal)
        self.slider_gain.setRange(0, 100)
        self.slider_gain.setValue(50)
        self.label_gain = QLabel("50")
        self.slider_gain.valueChanged.connect(lambda v: self.label_gain.setText(str(v)))
        self.slider_gain.valueChanged.connect(lambda v: self.param_changed.emit("GAIN", v))
        controls_layout.addWidget(self.slider_gain, row, 1)
        controls_layout.addWidget(self.label_gain, row, 2)
        row += 1

        controls_layout.addWidget(QLabel("Confidence:"), row, 0)
        self.slider_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_conf.setRange(0, 100)
        self.slider_conf.setValue(50)
        self.label_conf = QLabel("50")
        self.slider_conf.valueChanged.connect(lambda v: self.label_conf.setText(str(v)))
        self.slider_conf.valueChanged.connect(lambda v: self.confidence_changed.emit(v))
        controls_layout.addWidget(self.slider_conf, row, 1)
        controls_layout.addWidget(self.label_conf, row, 2)
        row += 1

        controls_layout.addWidget(QLabel("Texture Conf:"), row, 0)
        self.slider_disp = QSlider(Qt.Orientation.Horizontal)
        self.slider_disp.setRange(0, 100)
        self.slider_disp.setValue(100)
        self.label_disp = QLabel("100")
        self.slider_disp.valueChanged.connect(lambda v: self.label_disp.setText(str(v)))
        self.slider_disp.valueChanged.connect(lambda v: self.disparity_changed.emit(v))
        controls_layout.addWidget(self.slider_disp, row, 1)
        controls_layout.addWidget(self.label_disp, row, 2)
        row += 1

        self.btn_reset = QPushButton("Reset Camera Params")
        self.btn_reset.clicked.connect(self.reset_defaults)
        controls_layout.addWidget(self.btn_reset, row, 0, 1, 3)
        root_layout.addWidget(grp_controls)

        grp_device = QGroupBox("Device Info")
        device_layout = QGridLayout()
        grp_device.setLayout(device_layout)
        device_layout.addWidget(QLabel("Summary:"), 0, 0)
        self.lbl_device_summary = QLabel("Camera unavailable")
        self.lbl_device_summary.setWordWrap(True)
        device_layout.addWidget(self.lbl_device_summary, 0, 1)
        device_layout.addWidget(QLabel("Backend:"), 1, 0)
        self.lbl_backend_summary = QLabel("Backend: unavailable")
        self.lbl_backend_summary.setWordWrap(True)
        device_layout.addWidget(self.lbl_backend_summary, 1, 1)
        root_layout.addWidget(grp_device)

        grp_sensors = QGroupBox("Sensors")
        sensor_layout = QGridLayout()
        grp_sensors.setLayout(sensor_layout)
        sensor_layout.addWidget(QLabel("IMU:"), 0, 0)
        self.lbl_imu = QLabel("IMU unavailable")
        self.lbl_imu.setWordWrap(True)
        sensor_layout.addWidget(self.lbl_imu, 0, 1)
        sensor_layout.addWidget(QLabel("Gyroscope:"), 1, 0)
        self.lbl_gyro = QLabel("N/A")
        self.lbl_gyro.setWordWrap(True)
        sensor_layout.addWidget(self.lbl_gyro, 1, 1)
        sensor_layout.addWidget(QLabel("Acceleration:"), 2, 0)
        self.lbl_accel = QLabel("N/A")
        self.lbl_accel.setWordWrap(True)
        sensor_layout.addWidget(self.lbl_accel, 2, 1)
        sensor_layout.addWidget(QLabel("Magnetometer:"), 3, 0)
        self.lbl_mag = QLabel("Magnetometer unavailable")
        self.lbl_mag.setWordWrap(True)
        sensor_layout.addWidget(self.lbl_mag, 3, 1)
        sensor_layout.addWidget(QLabel("Barometer:"), 4, 0)
        self.lbl_baro = QLabel("Barometer unavailable")
        self.lbl_baro.setWordWrap(True)
        sensor_layout.addWidget(self.lbl_baro, 4, 1)
        root_layout.addWidget(grp_sensors)

        grp_health = QGroupBox("Health / Runtime Status")
        health_layout = QGridLayout()
        grp_health.setLayout(health_layout)
        health_layout.addWidget(QLabel("Health:"), 0, 0)
        self.lbl_health = QLabel("Health status unavailable")
        self.lbl_health.setWordWrap(True)
        health_layout.addWidget(self.lbl_health, 0, 1)
        health_layout.addWidget(QLabel("Grab Status:"), 1, 0)
        self.lbl_grab = QLabel("Last grab: N/A")
        self.lbl_grab.setWordWrap(True)
        health_layout.addWidget(self.lbl_grab, 1, 1)
        root_layout.addWidget(grp_health)

        grp_preview = QGroupBox("Local Camera Preview")
        preview_layout = QVBoxLayout()
        grp_preview.setLayout(preview_layout)
        self.lbl_preview = QLabel("NO CAMERA PREVIEW")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("background-color: black; color: white; border: 1px solid #555;")
        self.lbl_preview.setMinimumSize(320, 180)
        self.lbl_preview_status = QLabel("NO CAMERA PREVIEW")
        self.lbl_preview_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.lbl_preview)
        preview_layout.addWidget(self.lbl_preview_status)
        root_layout.addWidget(grp_preview)

        grp_stream = QGroupBox("ZED SDK Streaming (RTP)")
        grp_stream.setStyleSheet("color: #e67e22; border: 1px solid #e67e22;")
        stream_layout = QGridLayout()
        grp_stream.setLayout(stream_layout)

        stream_layout.addWidget(QLabel("Codec:"), 0, 0)
        self.combo_codec = QComboBox()
        self.combo_codec.addItems(["H264", "H265"])
        self.combo_codec.setEnabled(False)
        stream_layout.addWidget(self.combo_codec, 0, 1)

        stream_layout.addWidget(QLabel("Bitrate:"), 0, 2)
        self.combo_stream_bitrate = QComboBox()
        self.combo_stream_bitrate.addItems(["5000", "8000", "10000", "15000", "20000"])
        self.combo_stream_bitrate.setCurrentIndex(2)
        self.combo_stream_bitrate.setEnabled(False)
        stream_layout.addWidget(self.combo_stream_bitrate, 0, 3)

        stream_layout.addWidget(QLabel("Port:"), 1, 0)
        self.input_port = QLineEdit("30000")
        self.input_port.setEnabled(False)
        stream_layout.addWidget(self.input_port, 1, 1)

        self.btn_rtp_stream = QPushButton("Start RTP Stream")
        self.btn_rtp_stream.setCheckable(True)
        self.btn_rtp_stream.setEnabled(False)
        self.btn_rtp_stream.clicked.connect(self.on_rtp_stream_toggled)
        stream_layout.addWidget(self.btn_rtp_stream, 1, 2, 1, 2)

        stream_layout.addWidget(QLabel("Status:"), 2, 0)
        self.lbl_stream_status = QLabel("Stopped")
        self.lbl_stream_status.setWordWrap(True)
        stream_layout.addWidget(self.lbl_stream_status, 2, 1, 1, 3)
        root_layout.addWidget(grp_stream)

        self.set_rtp_stream_ui_state(False)

    def on_rtp_stream_toggled(self):
        enabled = self.btn_rtp_stream.isChecked()
        codec = self.combo_codec.currentText()
        bitrate = int(self.combo_stream_bitrate.currentText())
        try:
            port = int(self.input_port.text())
        except ValueError:
            port = 30000
            self.input_port.setText(str(port))

        self.set_rtp_stream_ui_state(enabled)
        self.rtp_stream_requested.emit(enabled, codec, bitrate, port)

    def set_rtp_stream_ui_state(self, active):
        state = build_rtp_stream_ui_state(active)
        self.btn_rtp_stream.setChecked(state["checked"])
        self.btn_rtp_stream.setText(state["text"])
        self.btn_rtp_stream.setStyleSheet(state["style"])

    def on_camera_connection_clicked(self):
        self.camera_connection_requested.emit(not self.connected)

    def set_camera_connection_state(self, connected):
        self.connected = bool(connected)
        if self.connected:
            self.btn_camera_connection.setText("Disconnect Camera")
            self.btn_camera_connection.setStyleSheet("background-color: #c0392b; color: white;")
        else:
            self.btn_camera_connection.setText("Connect Camera")
            self.btn_camera_connection.setStyleSheet("")

    def on_auto_exposure_toggled(self, checked):
        self.slider_exposure.setDisabled(checked or not self.connected)
        self.auto_exposure_toggled.emit(checked)

    def on_auto_wb_toggled(self, checked):
        self.slider_wb.setDisabled(checked or not self.connected)
        self.auto_wb_toggled.emit(checked)

    def on_mode_changed(self, index):
        self.capture_mode_changed.emit(self.combo_mode.currentText())

    def on_auto_focus_toggled(self, checked):
        self.slider_focus.setDisabled(checked or not self.connected or not self.slider_focus.isEnabled())
        self.auto_focus_toggled.emit(checked)

    def reset_defaults(self):
        self.chk_auto_exposure.setChecked(False)
        self.slider_exposure.setValue(60)
        self.chk_auto_wb.setChecked(False)
        self.slider_wb.setValue(5500)
        self.slider_gain.setValue(10)
        self.slider_conf.setValue(50)
        self.slider_disp.setValue(100)
        self.combo_mode.setCurrentIndex(0)
        self.chk_auto_focus.setChecked(False)
        self.slider_focus.setValue(65)

    def set_connected(self, connected):
        self.set_camera_connection_state(connected)
        if not connected:
            self.setTitle("ZED-M Camera Parameters (Disconnected)")
            self.clear_preview()
        else:
            self.setTitle("ZED-M Camera Parameters (Connected)")

    def update_info(self, res, fps):
        self.label_res_info.setText(f"Resolution: {res}")
        self.label_fps_info.setText(f"FPS: {fps}")

    def update_runtime(self, device_info, sensor_snapshot, health_status, streaming_status):
        state = build_camera_panel_state(
            device_info=device_info,
            sensor_snapshot=sensor_snapshot,
            health_status=health_status,
            streaming_status=streaming_status,
        )

        self.set_connected(device_info.get("connected", False))
        self.lbl_device_summary.setText(state["device_summary"])
        self.lbl_backend_summary.setText(state["backend_summary"])
        self.lbl_imu.setText(state["imu_summary"])
        self.lbl_gyro.setText(state["imu_gyro_summary"])
        self.lbl_accel.setText(state["imu_accel_summary"])
        self.lbl_mag.setText(state["mag_summary"])
        self.lbl_baro.setText(state["baro_summary"])
        self.lbl_health.setText(state["health_summary"])
        self.lbl_grab.setText(state["grab_summary"])
        self.lbl_stream_status.setText(state["streaming_summary"])

        controls = state["control_state"]
        self.combo_mode.setEnabled(self.connected)
        self.chk_auto_exposure.setEnabled(self.connected)
        self.chk_auto_wb.setEnabled(self.connected)
        self.slider_gain.setEnabled(self.connected)
        self.btn_reset.setEnabled(self.connected)
        self.slider_exposure.setEnabled(self.connected and not self.chk_auto_exposure.isChecked())
        self.slider_wb.setEnabled(self.connected and not self.chk_auto_wb.isChecked())
        self.chk_auto_focus.setEnabled(controls["auto_focus_enabled"])
        self.slider_focus.setEnabled(
            controls["manual_focus_enabled"] and not self.chk_auto_focus.isChecked()
        )
        self.slider_conf.setEnabled(controls["depth_controls_enabled"])
        self.slider_disp.setEnabled(controls["depth_controls_enabled"])
        self.combo_codec.setEnabled(controls["streaming_enabled"])
        self.combo_stream_bitrate.setEnabled(controls["streaming_enabled"])
        self.input_port.setEnabled(controls["streaming_enabled"])
        self.btn_rtp_stream.setEnabled(controls["streaming_enabled"])
        self.set_rtp_stream_ui_state(streaming_status.get("enabled", False))

    def update_preview(self, cv_image):
        if cv_image is None:
            return

        if not hasattr(cv_image, "shape") or len(cv_image.shape) != 3:
            self.lbl_preview.setText("PREVIEW UNAVAILABLE")
            return

        h, w, ch = cv_image.shape
        bytes_per_line = ch * w
        rgb_image = cv_image[:, :, [2, 1, 0]].copy()
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        scaled = pixmap.scaled(self.lbl_preview.size(), Qt.AspectRatioMode.KeepAspectRatio)
        self.lbl_preview.setPixmap(scaled)
        self.lbl_preview.setText("")
        self.lbl_preview_status.setText("LIVE PREVIEW")

    def clear_preview(self):
        self.lbl_preview.clear()
        self.lbl_preview.setText("NO CAMERA PREVIEW")
        self.lbl_preview_status.setText("NO CAMERA PREVIEW")

    def set_preview_status(self, text):
        self.lbl_preview_status.setText(text)
