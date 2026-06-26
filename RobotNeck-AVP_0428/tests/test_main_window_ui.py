import importlib
import os
import sys
import types


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)


class Signal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class QWidget:
    def __init__(self, parent=None):
        self.parent = parent
        self._layout = None
        self._enabled = True
        self._style = ""

    def setLayout(self, layout):
        self._layout = layout

    def setEnabled(self, value):
        self._enabled = value

    def isEnabled(self):
        return self._enabled

    def setStyleSheet(self, style):
        self._style = style


class QMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.central_widget = None
        self.status_bar = None
        self.window_title = ""

    def setCentralWidget(self, widget):
        self.central_widget = widget

    def setStatusBar(self, status_bar):
        self.status_bar = status_bar

    def setWindowTitle(self, title):
        self.window_title = title

    def resize(self, width, height):
        self.size = (width, height)

    def close(self):
        self.closed = True


class Layout:
    def __init__(self, *args, **kwargs):
        self.items = []

    def addWidget(self, widget, *args):
        self.items.append(("widget", widget, args))

    def addLayout(self, layout, *args):
        self.items.append(("layout", layout, args))

    def addStretch(self):
        self.items.append(("stretch",))


class QVBoxLayout(Layout):
    pass


class QHBoxLayout(Layout):
    pass


class QTabWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._tabs = []
        self._index = 0
        self.currentChanged = Signal()

    def addTab(self, widget, label):
        self._tabs.append((widget, label))

    def count(self):
        return len(self._tabs)

    def tabText(self, index):
        return self._tabs[index][1]

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, index):
        self._index = index
        self.currentChanged.emit(index)


class QPushButton(QWidget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self.clicked = Signal()
        self._flat = False
        self._checkable = False
        self._checked = False
        self._signals_blocked = False

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def click(self):
        if not self.isEnabled():
            return
        if self._checkable:
            self._checked = not self._checked
        self.clicked.emit()

    def setFlat(self, flat):
        self._flat = flat

    def setCheckable(self, checkable):
        self._checkable = bool(checkable)

    def setChecked(self, checked):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked

    def blockSignals(self, blocked):
        self._signals_blocked = bool(blocked)


class QStatusBar(QWidget):
    def __init__(self):
        super().__init__()
        self.message = ""
        self.widgets = []

    def showMessage(self, message):
        self.message = message

    def addPermanentWidget(self, widget):
        self.widgets.append(widget)


class QMessageBox:
    warnings = []
    criticals = []

    class StandardButton:
        Yes = 1
        No = 2

    @classmethod
    def question(cls, *args, **kwargs):
        return cls.StandardButton.Yes

    @classmethod
    def critical(cls, *args, **kwargs):
        cls.criticals.append((args, kwargs))
        return None

    @classmethod
    def warning(cls, *args, **kwargs):
        cls.warnings.append((args, kwargs))
        return None


class QFileDialog:
    save_result = ("", "")
    open_result = ("", "")

    @staticmethod
    def getSaveFileName(*args, **kwargs):
        return QFileDialog.save_result

    @staticmethod
    def getOpenFileName(*args, **kwargs):
        return QFileDialog.open_result


class QTimer:
    def __init__(self):
        self.timeout = Signal()
        self.started = False

    def start(self, *args):
        self.started = True

    def stop(self):
        self.started = False


def pyqtSignal(*args, **kwargs):
    return Signal()


class Qt:
    pass


class QIcon:
    pass


class FakeCheckbox:
    def isChecked(self):
        return False


class FakePoseControlWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.is_tracking = False
        self.dependencies = None
        self.export_calls = 0
        self.restore_calls = []
        self.toggle_calls = []
        self.btn_track_clicks = 0
        self.calibrate_calls = 0
        self.manual_initial_pose = {"yaw": 0.0, "pitch": 0.0}
        self.manual_adjust_active = False
        self.btn_track = QPushButton("Start Tracking")
        self.btn_track.clicked.connect(self._on_btn_track_clicked)

    def set_dependencies(self, motors, client, camera_controller=None):
        self.dependencies = (motors, client, camera_controller)

    def export_tracking_runtime_state(self):
        self.export_calls += 1
        return {
            "was_tracking": self.is_tracking,
            "tracking_start_pose": {"yaw": 123, "pitch": 456},
            "retargeter_state": {
                "yaw_offset": 1.25,
                "pitch_offset": -0.75,
                "calibrated": True,
            },
        }

    def restore_tracking_runtime_state(self, state):
        self.restore_calls.append(state)
        self.is_tracking = bool(state.get("was_tracking", False))

    def toggle_tracking(self, checked):
        self.toggle_calls.append(bool(checked))
        self.is_tracking = checked

    def _on_btn_track_clicked(self):
        self.btn_track_clicks += 1
        self.toggle_tracking(not self.is_tracking)

    def get_runtime_status(self):
        return {
            "yaw_inactive": False,
            "yaw_inactive_reason": "",
            "tracking_enabled": not self.manual_adjust_active,
            "tracking_block_reason": (
                "Finish manual adjust before starting tracking." if self.manual_adjust_active else ""
            ),
            "manual_adjust_active": self.manual_adjust_active,
            "pose_fresh": True,
            "pose_reason": "ok",
            "pose_age_ms": 12.5,
            "last_pose_timestamp": 123.0,
            "loop_dt_ms": 16.7,
            "loop_rate_hz": 59.88,
            "stale_pose_count": 2,
            "last_motor_command_timestamp": 124.0,
            "motor_command_gap_ms": 18.0,
            "last_command_targets_deg": {"yaw": 10.0, "pitch": -5.0},
        }

    def get_manual_initial_pose(self):
        return dict(self.manual_initial_pose)

    def set_manual_initial_pose(self, yaw, pitch):
        self.manual_initial_pose = {"yaw": float(yaw), "pitch": float(pitch)}

    def calibrate(self):
        self.calibrate_calls += 1


class FakeCameraParamWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.connected = False
        self.preview_frame = None
        self.preview_cleared = 0
        self.preview_status = "NO CAMERA PREVIEW"
        self.param_changed = Signal()
        self.auto_exposure_toggled = Signal()
        self.auto_wb_toggled = Signal()
        self.confidence_changed = Signal()
        self.disparity_changed = Signal()
        self.capture_mode_changed = Signal()
        self.focus_changed = Signal()
        self.auto_focus_toggled = Signal()
        self.rtp_stream_requested = Signal()
        self.camera_connection_requested = Signal()
        self.btn_rtp_stream = QPushButton()

    def set_connected(self, connected):
        self.connected = connected

    def update_runtime(self, **kwargs):
        self.runtime = kwargs

    def update_info(self, res, fps):
        self.info = (res, fps)

    def set_rtp_stream_ui_state(self, checked):
        self.rtp_state = checked

    def update_preview(self, frame):
        self.preview_frame = frame
        self.preview_status = "LIVE PREVIEW"

    def clear_preview(self):
        self.preview_frame = None
        self.preview_cleared += 1
        self.preview_status = "NO CAMERA PREVIEW"

    def set_preview_status(self, text):
        self.preview_status = text


class FakeTeleopStreamWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.is_streaming = False
        self.start_stream_requested = Signal()
        self.stop_stream_requested = Signal()
        self.restart_stream_requested = Signal()
        self.chk_mirror = FakeCheckbox()
        self.chk_rotate = FakeCheckbox()

    def get_config(self):
        return "3840x1080", 30, 20000, True, "Balanced"

    def update_frame(self, frame):
        self.frame = frame

    def update_stats(self, *args):
        self.stats = args

    def set_streaming_state(self, state):
        self.is_streaming = state


class FakeDxlDebugWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.motor_connected = Signal()
        self.monitor_started = False
        self.monitor_page_active = False
        self.connected = False
        self.btn_connect = QPushButton()
        self.connection_requests = []
        self.monitor_sync_calls = 0
        self.motor_controller = None

    def request_connection(self, should_connect):
        self.connection_requests.append(bool(should_connect))
        self.connected = bool(should_connect)
        self.motor_controller = types.SimpleNamespace(connected=self.connected) if self.connected else None
        if self.connected:
            self._sync_monitoring_timer()
        else:
            self._stop_monitoring_timer()

    def start_monitoring(self):
        self.monitor_page_active = True
        self._sync_monitoring_timer()

    def stop_monitoring(self):
        self.monitor_page_active = False
        self._stop_monitoring_timer()

    def _sync_monitoring_timer(self):
        self.monitor_sync_calls += 1
        self.monitor_started = bool(self.monitor_page_active and self.connected)

    def _stop_monitoring_timer(self):
        self.monitor_started = False

    def clean_shutdown(self):
        self._stop_monitoring_timer()
        self.cleaned = True


class FakeDashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.snapshot = None
        self.avp_runtime = None
        self.avp_settings = {"ip": "172.20.10.2", "auto_reconnect": False}
        self.connect_avp_requested = Signal()
        self.disconnect_avp_requested = Signal()
        self.retry_avp_requested = Signal()
        self.check_avp_requested = Signal()
        self.connect_camera_requested = Signal()
        self.disconnect_camera_requested = Signal()
        self.connect_motor_requested = Signal()
        self.disconnect_motor_requested = Signal()
        self.start_stream_requested = Signal()
        self.stop_stream_requested = Signal()
        self.toggle_tracking_requested = Signal()
        self.calibrate_requested = Signal()
        self.recovery_action_requested = Signal()

    def update_system_snapshot(self, snapshot):
        self.snapshot = snapshot

    def update_avp_runtime(self, runtime, pose_status=None, tracking_runtime=None):
        self.avp_runtime = {
            "runtime": runtime,
            "pose_status": pose_status,
            "tracking_runtime": tracking_runtime,
        }

    def get_avp_settings(self):
        return dict(self.avp_settings)

    def set_avp_settings(self, ip, auto_reconnect):
        self.avp_settings = {"ip": ip, "auto_reconnect": bool(auto_reconnect)}


class FakeClient:
    def __init__(self, ip=None):
        self.ip = ip or "172.20.10.2"
        self.connect_calls = []
        self.disconnect_calls = 0
        self.retry_calls = 0
        self.stream_start_calls = []
        self.stream_stop_calls = 0
        self.connection_status = {
            "state": "idle",
            "ip": self.ip,
            "auto_reconnect": False,
            "session_mode": "tracking_only",
            "last_error": None,
            "state_age_sec": 0.0,
            "last_sample_timestamp": None,
            "has_ever_received_pose": False,
        }
        self.pose_status = {"valid": False, "reason": "idle", "fresh": False}

    def connect(self, ip=None, auto_reconnect=False, session_mode="tracking_only"):
        self.connect_calls.append(
            {
                "ip": ip or self.ip,
                "auto_reconnect": bool(auto_reconnect),
                "session_mode": session_mode,
            }
        )
        self.ip = ip or self.ip
        self.connection_status.update(
            {
                "state": "connecting",
                "ip": self.ip,
                "auto_reconnect": bool(auto_reconnect),
                "session_mode": session_mode,
            }
        )
        return True

    def disconnect(self):
        self.disconnect_calls += 1
        self.connection_status["state"] = "disconnected"

    def retry_now(self):
        self.retry_calls += 1
        self.connection_status["state"] = "reconnecting"
        return True

    def start_video_stream(self, *args, **kwargs):
        self.stream_start_calls.append({"args": args, "kwargs": kwargs})
        self.connection_status["state"] = "ready"
        self.connection_status["session_mode"] = "streaming"
        return True

    def stop_video_stream(self):
        self.stream_stop_calls += 1
        self.connection_status["session_mode"] = "tracking_only"
        return True

    def restart_video_stream(self, *args, **kwargs):
        return True

    def get_connection_status(self):
        return dict(self.connection_status)

    def get_pose_status(self):
        return dict(self.pose_status)


class FakeCameraController:
    def __init__(self):
        self.is_connected = False
        self.open_calls = []
        self.close_calls = 0
        self.streaming_enabled = False

    def open_camera(self, resolution=None, fps=None):
        self.open_calls.append((resolution, fps))
        self.is_connected = True
        return object()

    def close_camera(self):
        self.close_calls += 1
        self.is_connected = False

    def read(self):
        return False, None

    def get_device_info(self):
        return {}

    def get_sensor_snapshot(self):
        return {}

    def get_health_status(self):
        return {}

    def get_streaming_status(self):
        return {"enabled": self.streaming_enabled}

    def enable_streaming(self, **kwargs):
        self.streaming_enabled = True
        return True

    def disable_streaming(self):
        self.streaming_enabled = False
        return True

    def set_exposure(self, value):
        return True

    def set_whitebalance(self, value):
        return True

    def set_gain(self, value):
        return True

    def set_auto_exposure(self, enabled):
        return True

    def set_auto_whitebalance(self, enabled):
        return True

    def set_confidence_threshold(self, value):
        return True

    def set_disparity_range(self, value):
        return True

    def set_view_mode(self, mode):
        return True

    def set_focus(self, value):
        return True

    def set_auto_focus(self, enabled):
        return True


class FakeAVPSessionCoordinator:
    def __init__(self, client_factory, wait_timeout_sec=2.0, poll_interval_sec=0.05):
        self.client_factory = client_factory
        self.calls = []

    def switch_mode(
        self,
        current_client,
        target_mode,
        ip,
        auto_reconnect,
        export_runtime_state=None,
        restore_runtime_state=None,
        stop_tracking=None,
        attach_client=None,
    ):
        self.calls.append(
            {
                "current_client": current_client,
                "target_mode": target_mode,
                "ip": ip,
                "auto_reconnect": auto_reconnect,
            }
        )
        runtime_state = export_runtime_state() if export_runtime_state else {}
        if stop_tracking is not None:
            stop_tracking()
        new_client = self.client_factory(ip)
        new_client.connect(ip=ip, auto_reconnect=auto_reconnect, session_mode=target_mode)
        new_client.connection_status["state"] = "ready"
        new_client.connection_status["session_mode"] = target_mode
        new_client.pose_status = {"valid": True, "reason": "ready", "fresh": True}
        if attach_client is not None:
            attach_client(new_client)
        if restore_runtime_state is not None:
            restore_runtime_state(runtime_state)
        return types.SimpleNamespace(success=True, client=new_client, reason="")


def load_main_window(monkeypatch):
    pyqt6 = types.ModuleType("PyQt6")
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")
    qtcore = types.ModuleType("PyQt6.QtCore")
    qtgui = types.ModuleType("PyQt6.QtGui")

    qtwidgets.QMainWindow = QMainWindow
    qtwidgets.QWidget = QWidget
    qtwidgets.QVBoxLayout = QVBoxLayout
    qtwidgets.QTabWidget = QTabWidget
    qtwidgets.QPushButton = QPushButton
    qtwidgets.QStatusBar = QStatusBar
    qtwidgets.QMessageBox = QMessageBox
    qtwidgets.QHBoxLayout = QHBoxLayout
    qtwidgets.QFileDialog = QFileDialog
    qtcore.Qt = Qt
    qtcore.QTimer = QTimer
    qtcore.pyqtSignal = pyqtSignal
    qtgui.QIcon = QIcon

    monkeypatch.setitem(sys.modules, "PyQt6", pyqt6)
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", qtwidgets)
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", qtcore)
    monkeypatch.setitem(sys.modules, "PyQt6.QtGui", qtgui)
    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace())

    monkeypatch.setitem(sys.modules, "src.gui.pose_control", types.SimpleNamespace(PoseControlWidget=FakePoseControlWidget))
    monkeypatch.setitem(sys.modules, "src.gui.camera_param", types.SimpleNamespace(CameraParamWidget=FakeCameraParamWidget))
    monkeypatch.setitem(sys.modules, "src.gui.teleop_stream", types.SimpleNamespace(TeleopStreamWidget=FakeTeleopStreamWidget))
    monkeypatch.setitem(sys.modules, "src.gui.dynamixel_debug", types.SimpleNamespace(DxlDebugWidget=FakeDxlDebugWidget))
    monkeypatch.setitem(sys.modules, "src.gui.dashboard", types.SimpleNamespace(DashboardWidget=FakeDashboardWidget))
    monkeypatch.setitem(sys.modules, "src.core.camera_controller", types.SimpleNamespace(CameraController=FakeCameraController))
    monkeypatch.setitem(sys.modules, "src.core.client", types.SimpleNamespace(AVPClient=FakeClient))
    monkeypatch.setitem(sys.modules, "src.core.mock_client", types.SimpleNamespace(MockAVPClient=FakeClient))
    monkeypatch.setitem(
        sys.modules,
        "src.core.avp_session",
        types.SimpleNamespace(AVPSessionCoordinator=FakeAVPSessionCoordinator),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.core.avp_connection",
        types.SimpleNamespace(
            load_avp_connection_settings=lambda: {"ip": "172.20.10.2", "auto_reconnect": False},
            save_avp_connection_settings=lambda ip, auto_reconnect: {"ip": ip, "auto_reconnect": auto_reconnect},
        ),
    )

    sys.modules.pop("src.gui.main_window", None)
    return importlib.import_module("src.gui.main_window")


def test_main_window_uses_dashboard_first_without_auto_avp_connect(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()

    assert window.tabs.count() == 5
    assert window.tabs.tabText(0) == "Dashboard"
    assert window.tabs.tabText(1) == "Pose Control"
    assert window.tabs.tabText(2) == "ZED-M Camera"
    assert window.tabs.tabText(3) == "VisionPro Stream"
    assert window.tabs.tabText(4) == "Dynamixel Debug"
    assert window.client is None
    assert window.dashboard_widget.get_avp_settings() == {
        "ip": "172.20.10.2",
        "auto_reconnect": False,
    }


def test_connect_avp_from_dashboard_creates_client_and_uses_saved_settings(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.dashboard_widget.set_avp_settings(ip="192.168.0.12", auto_reconnect=True)

    window.connect_avp_from_dashboard()

    assert window.client is not None
    assert window.client.connect_calls == [
        {"ip": "192.168.0.12", "auto_reconnect": True, "session_mode": "tracking_only"}
    ]


def test_connect_camera_from_dashboard_is_independent_from_avp(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()

    window.connect_camera_from_dashboard()

    assert window.camera_controller.open_calls == [("3840x1080", 30)]
    assert window.teleop_widget.is_streaming is False


def test_start_stream_requires_connected_avp_session(monkeypatch):
    main_window = load_main_window(monkeypatch)

    QMessageBox.warnings.clear()
    window = main_window.MainWindow()
    window.client = FakeClient()

    started = window.start_stream()

    assert started is False
    assert window.teleop_widget.is_streaming is False
    assert QMessageBox.warnings == []
    assert window.status_bar.message == "VisionPro stream start blocked: AVP session is not connected (idle)."


def test_start_stream_without_client_uses_non_blocking_runtime_message(monkeypatch):
    main_window = load_main_window(monkeypatch)

    QMessageBox.warnings.clear()
    window = main_window.MainWindow()

    started = window.start_stream()

    assert started is False
    assert window.teleop_widget.is_streaming is False
    assert QMessageBox.warnings == []
    assert window.status_bar.message == "VisionPro stream start skipped: AVP client is not ready yet."


def test_start_stream_allows_switch_when_waiting_for_first_pose(monkeypatch):
    main_window = load_main_window(monkeypatch)

    QMessageBox.warnings.clear()
    window = main_window.MainWindow()
    window.client = FakeClient("172.20.10.2")
    window.camera_controller.is_connected = True
    window.client.connection_status.update({"state": "connected_waiting_first_sample", "session_mode": "tracking_only"})
    window.client.pose_status = {"valid": False, "reason": "waiting_first_sample", "fresh": False}

    started = window.start_stream()

    assert started is True
    assert QMessageBox.warnings == []
    assert window.status_bar.message == "VisionPro stream started."
    assert window.client.stream_start_calls


def test_start_stream_rebuilds_tracking_only_client_and_restores_tracking_state(monkeypatch):
    main_window = load_main_window(monkeypatch)

    created_clients = []

    class RebuildClient(FakeClient):
        def __init__(self, ip=None):
            super().__init__(ip=ip)
            created_clients.append(self)

    window = main_window.MainWindow()
    window._create_client = lambda ip: RebuildClient(ip)
    window.camera_controller.is_connected = True

    original_client = RebuildClient("172.20.10.2")
    original_client.connection_status.update({"state": "ready", "session_mode": "tracking_only"})
    original_client.pose_status = {"valid": True, "reason": "ready", "fresh": True}
    window.client = original_client
    window.pose_widget.set_dependencies(window.motor_controller, window.client, window.camera_controller)
    window.pose_widget.is_tracking = True

    started = window.start_stream()

    assert started is True
    assert window.avp_session_coordinator.calls[-1]["current_client"] is original_client
    assert window.avp_session_coordinator.calls[-1]["target_mode"] == "streaming"
    assert len(created_clients) >= 2
    rebuilt_client = window.client
    assert rebuilt_client is not original_client
    assert rebuilt_client.connect_calls == [
        {"ip": "172.20.10.2", "auto_reconnect": False, "session_mode": "streaming"}
    ]
    assert rebuilt_client.stream_start_calls
    assert window.pose_widget.export_calls == 1
    assert window.pose_widget.restore_calls
    assert window.pose_widget.restore_calls[-1]["was_tracking"] is True


def test_stop_stream_rebuilds_streaming_client_and_restores_tracking_only_state(monkeypatch):
    main_window = load_main_window(monkeypatch)

    created_clients = []

    class RebuildClient(FakeClient):
        def __init__(self, ip=None):
            super().__init__(ip=ip)
            created_clients.append(self)

    window = main_window.MainWindow()
    window._create_client = lambda ip: RebuildClient(ip)
    window.camera_controller.is_connected = True
    window.teleop_widget.set_streaming_state(True)

    original_client = RebuildClient("172.20.10.2")
    original_client.connection_status.update({"state": "ready", "session_mode": "streaming"})
    original_client.pose_status = {"valid": True, "reason": "ready", "fresh": True}
    window.client = original_client
    window.pose_widget.set_dependencies(window.motor_controller, window.client, window.camera_controller)
    window.pose_widget.is_tracking = True

    stopped = window.stop_stream()

    assert stopped is True
    assert window.avp_session_coordinator.calls[-1]["current_client"] is original_client
    assert window.avp_session_coordinator.calls[-1]["target_mode"] == "tracking_only"
    rebuilt_client = window.client
    assert rebuilt_client is not original_client
    assert rebuilt_client.connect_calls == [
        {"ip": "172.20.10.2", "auto_reconnect": False, "session_mode": "tracking_only"}
    ]
    assert window.teleop_widget.is_streaming is False
    assert window.pose_widget.export_calls == 1
    assert window.pose_widget.restore_calls
    assert window.pose_widget.restore_calls[-1]["was_tracking"] is True


def test_update_loop_skips_teleop_preview_when_stream_is_stopped(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.camera_controller.is_connected = True
    window.teleop_widget.set_streaming_state(False)
    window.tabs.setCurrentIndex(3)
    window.teleop_widget.frame = "old-frame"

    window.camera_controller.read = lambda: (True, "fresh-frame")

    window.update_loop()

    assert window.teleop_widget.frame == "old-frame"


def test_update_loop_updates_camera_preview_when_camera_tab_is_active(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.camera_controller.is_connected = True
    window.tabs.setCurrentIndex(2)
    window.camera_controller.read = lambda: (True, "camera-frame")

    window.update_loop()

    assert window.camera_widget.preview_frame == "camera-frame"


def test_update_loop_skips_camera_preview_when_camera_is_disconnected(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.tabs.setCurrentIndex(2)
    window.camera_widget.preview_frame = "old-camera-frame"
    window.camera_controller.read = lambda: (True, "fresh-camera-frame")

    window.update_loop()

    assert window.camera_widget.preview_frame == "old-camera-frame"


def test_disconnecting_camera_clears_camera_preview(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.camera_controller.is_connected = True
    window.camera_widget.preview_frame = "stale-frame"
    window.on_camera_connection_requested(False)

    assert window.camera_widget.preview_frame is None
    assert window.camera_widget.preview_cleared >= 1
    assert window.camera_widget.preview_status == "NO CAMERA PREVIEW"


def test_update_loop_marks_camera_preview_as_no_signal_when_frame_read_fails(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.camera_controller.is_connected = True
    window.tabs.setCurrentIndex(2)
    window.camera_widget.preview_frame = "old-camera-frame"
    window.camera_controller.read = lambda: (False, None)

    window.update_loop()

    assert window.camera_widget.preview_frame == "old-camera-frame"
    assert window.camera_widget.preview_status == "NO CAMERA SIGNAL"


def test_update_loop_skips_camera_diagnostics_when_env_disables_them(monkeypatch):
    monkeypatch.setenv("ROBO_NECK_DISABLE_CAMERA_DIAGNOSTICS", "1")
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    calls = []
    window.refresh_camera_diagnostics = lambda force=False: calls.append(force)

    window.update_loop()

    assert calls == []


def test_start_stop_start_cycle_rebuilds_sessions_cleanly(monkeypatch):
    main_window = load_main_window(monkeypatch)

    created_clients = []

    class RebuildClient(FakeClient):
        def __init__(self, ip=None):
            super().__init__(ip=ip)
            created_clients.append(self)

    window = main_window.MainWindow()
    window._create_client = lambda ip: RebuildClient(ip)
    window.camera_controller.is_connected = True

    initial_client = RebuildClient("172.20.10.2")
    initial_client.connection_status.update({"state": "ready", "session_mode": "tracking_only"})
    initial_client.pose_status = {"valid": True, "reason": "ready", "fresh": True}
    window.client = initial_client
    window.pose_widget.set_dependencies(window.motor_controller, window.client, window.camera_controller)

    assert window.start_stream() is True
    streaming_client = window.client
    assert streaming_client is not initial_client
    assert streaming_client.connection_status["session_mode"] == "streaming"

    assert window.stop_stream() is True
    tracking_client = window.client
    assert tracking_client is not streaming_client
    assert tracking_client.connection_status["session_mode"] == "tracking_only"

    tracking_client.pose_status = {"valid": True, "reason": "ready", "fresh": True}
    tracking_client.connection_status["state"] = "ready"

    assert window.start_stream() is True
    restarted_streaming_client = window.client
    assert restarted_streaming_client is not tracking_client
    assert restarted_streaming_client.connection_status["session_mode"] == "streaming"


def test_start_stream_updates_runtime_message_on_success(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.camera_controller.is_connected = True
    client = FakeClient("172.20.10.2")
    client.connection_status.update({"state": "ready", "session_mode": "streaming"})
    client.pose_status = {"valid": True, "reason": "ready", "fresh": True}
    window.client = client
    window.pose_widget.set_dependencies(window.motor_controller, window.client, window.camera_controller)

    started = window.start_stream()

    assert started is True
    assert window.status_bar.message == "VisionPro stream started."


def test_stop_stream_updates_runtime_message_on_success(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.camera_controller.is_connected = True
    window.teleop_widget.set_streaming_state(True)
    client = FakeClient("172.20.10.2")
    client.connection_status.update({"state": "ready", "session_mode": "tracking_only"})
    window.client = client
    window.pose_widget.set_dependencies(window.motor_controller, window.client, window.camera_controller)

    stopped = window.stop_stream()

    assert stopped is True
    assert window.status_bar.message == "VisionPro stream stopped. AVP tracking remains available."


def test_start_stream_switch_failure_does_not_show_warning_dialog(monkeypatch):
    main_window = load_main_window(monkeypatch)

    QMessageBox.warnings.clear()
    window = main_window.MainWindow()
    window.client = FakeClient("172.20.10.2")
    window.client.connection_status.update({"state": "ready", "session_mode": "tracking_only"})
    window.client.pose_status = {"valid": True, "reason": "ready", "fresh": True}
    window.avp_session_coordinator.switch_mode = lambda **kwargs: types.SimpleNamespace(
        success=False, reason="mock switch failure"
    )

    started = window.start_stream()

    assert started is False
    assert QMessageBox.warnings == []
    assert window.status_bar.message == "VisionPro stream switch failed: mock switch failure"


def test_stop_stream_switch_failure_does_not_show_warning_dialog(monkeypatch):
    main_window = load_main_window(monkeypatch)

    QMessageBox.warnings.clear()
    window = main_window.MainWindow()
    window.client = FakeClient("172.20.10.2")
    window.client.connection_status.update({"state": "ready", "session_mode": "streaming"})
    window.teleop_widget.set_streaming_state(True)
    window.avp_session_coordinator.switch_mode = lambda **kwargs: types.SimpleNamespace(
        success=False, reason="mock stop failure"
    )

    stopped = window.stop_stream()

    assert stopped is False
    assert QMessageBox.warnings == []
    assert window.status_bar.message == "VisionPro stream stop failed: mock stop failure"


def test_dashboard_stop_stream_signal_stops_stream(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.camera_controller.is_connected = True
    window.teleop_widget.set_streaming_state(True)
    client = FakeClient("172.20.10.2")
    client.connection_status.update({"state": "ready", "session_mode": "tracking_only"})
    window.client = client
    window.pose_widget.set_dependencies(window.motor_controller, window.client, window.camera_controller)

    window.dashboard_widget.stop_stream_requested.emit()

    assert window.teleop_widget.is_streaming is False
    assert window.status_bar.message == "VisionPro stream stopped. AVP tracking remains available."


def test_dashboard_toggle_tracking_signal_toggles_pose_tracking(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()

    window.dashboard_widget.toggle_tracking_requested.emit()
    window.dashboard_widget.toggle_tracking_requested.emit()

    assert window.pose_widget.toggle_calls == [True, False]
    assert window.pose_widget.btn_track_clicks == 2
    assert window.status_bar.message == "Tracking stopped from Dashboard."


def test_dashboard_tracking_uses_pose_control_block_reason(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.pose_widget.manual_adjust_active = True
    window.refresh_system_snapshot()

    window.dashboard_widget.toggle_tracking_requested.emit()

    assert window.pose_widget.toggle_calls == []
    assert window.pose_widget.btn_track_clicks == 0
    assert window.status_bar.message == "Dashboard tracking blocked: Finish manual adjust before starting tracking."


def test_refresh_system_snapshot_forwards_pose_diagnostics_to_dashboard(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.client = FakeClient("172.20.10.2")
    window.client.connection_status.update({"state": "ready", "session_mode": "tracking_only"})
    window.client.pose_status = {
        "valid": False,
        "reason": "stale_sample",
        "fresh": False,
        "state_age_sec": 0.42,
        "last_sample_timestamp": 99.0,
    }
    window.propagate_dependencies()

    snapshot = window.refresh_system_snapshot()

    assert snapshot.pose_sample_reason == "stale_sample"
    assert window.dashboard_widget.avp_runtime["pose_status"]["reason"] == "stale_sample"
    assert window.dashboard_widget.avp_runtime["tracking_runtime"]["pose_age_ms"] == 12.5
    assert window.dashboard_widget.avp_runtime["tracking_runtime"]["loop_rate_hz"] == 59.88


def test_dashboard_motor_connect_signal_uses_dxl_debug_bridge(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()

    window.dashboard_widget.connect_motor_requested.emit()
    window.dashboard_widget.disconnect_motor_requested.emit()

    assert window.dxl_debug.connection_requests == [True, False]
    assert window.status_bar.message == "Motor disconnect requested from Dashboard."


def test_dxl_monitor_only_runs_on_debug_tab(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()

    window.connect_motor_from_dashboard()
    assert window.dxl_debug.monitor_started is False

    window.tabs.setCurrentIndex(4)
    assert window.dxl_debug.monitor_started is True

    window.tabs.setCurrentIndex(0)
    assert window.dxl_debug.monitor_started is False


def test_dxl_monitor_stops_before_disconnect(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.tabs.setCurrentIndex(4)
    window.connect_motor_from_dashboard()

    assert window.dxl_debug.monitor_started is True

    window.disconnect_motor_from_dashboard()

    assert window.dxl_debug.monitor_started is False


def test_dashboard_calibrate_signal_invokes_pose_control(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()

    window.dashboard_widget.calibrate_requested.emit()

    assert window.pose_widget.calibrate_calls == 1
    assert window.status_bar.message == "Calibration started from Dashboard."


def test_dashboard_disconnect_camera_signal_closes_camera(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.camera_controller.is_connected = True

    window.dashboard_widget.disconnect_camera_requested.emit()

    assert window.camera_controller.close_calls == 1


def test_dashboard_recovery_action_dispatches_to_camera_connect(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()

    window.dashboard_widget.recovery_action_requested.emit("connect_camera")

    assert window.camera_controller.open_calls == [("3840x1080", 30)]


def test_dashboard_recovery_action_dispatches_to_avp_check(monkeypatch):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    client = FakeClient("172.20.10.2")
    client.pose_status = {"valid": False, "reason": "waiting_first_sample", "fresh": False}
    window.client = client

    window.dashboard_widget.recovery_action_requested.emit("check_avp")

    assert window.status_bar.message == "AVP status: waiting_first_sample"


def test_rtp_request_without_camera_uses_non_blocking_runtime_message(monkeypatch):
    main_window = load_main_window(monkeypatch)

    QMessageBox.warnings.clear()
    window = main_window.MainWindow()

    window.on_rtp_stream_requested(True, "H264", 4000, 5004)

    assert QMessageBox.warnings == []
    assert window.camera_widget.rtp_state is False
    assert window.status_bar.message == "RTP stream blocked: Camera not connected."


def test_save_config_persists_avp_settings_and_manual_initial_pose(monkeypatch, tmpdir):
    main_window = load_main_window(monkeypatch)

    window = main_window.MainWindow()
    window.dashboard_widget.set_avp_settings(ip="192.168.0.12", auto_reconnect=True)
    window.pose_widget.set_manual_initial_pose(12.5, -8.0)

    target_path = tmpdir.join("ui_config.json")
    QFileDialog.save_result = (str(target_path), "JSON Files (*.json)")

    window.save_config()

    import json

    saved = json.loads(target_path.read())
    assert saved["avp"]["ip"] == "192.168.0.12"
    assert saved["avp"]["auto_reconnect"] is True
    assert saved["initial_pose"] == {"yaw": 12.5, "pitch": -8.0}


def test_load_config_applies_avp_settings_and_manual_initial_pose(monkeypatch, tmpdir):
    main_window = load_main_window(monkeypatch)

    config_path = tmpdir.join("ui_config.json")
    config_path.write(
        '{"avp": {"ip": "10.0.0.8", "auto_reconnect": true}, "initial_pose": {"yaw": 22.0, "pitch": -11.0}}',
    )
    QFileDialog.open_result = (str(config_path), "JSON Files (*.json)")

    window = main_window.MainWindow()
    window.dashboard_widget.set_avp_settings(ip="172.20.10.2", auto_reconnect=False)
    window.pose_widget.set_manual_initial_pose(0.0, 0.0)

    window.load_config()

    assert window.dashboard_widget.get_avp_settings() == {
        "ip": "10.0.0.8",
        "auto_reconnect": True,
    }
    assert window.pose_widget.get_manual_initial_pose() == {
        "yaw": 22.0,
        "pitch": -11.0,
    }
