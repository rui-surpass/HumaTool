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
        self._visible = True

    def setLayout(self, layout):
        self._layout = layout

    def setVisible(self, value):
        self._visible = bool(value)

    def isVisible(self):
        return self._visible


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


class QGridLayout(Layout):
    pass


class QLabel(QWidget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self._style = ""

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setObjectName(self, _name):
        return None

    def setWordWrap(self, _value):
        return None

    def setStyleSheet(self, style):
        self._style = style

    def styleSheet(self):
        return self._style


class QGroupBox(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._title = title
        self._style = ""
        self.set_title_calls = []

    def title(self):
        return self._title

    def setTitle(self, title):
        self._title = title
        self.set_title_calls.append(title)

    def setStyleSheet(self, style):
        self._style = style

    def styleSheet(self):
        return self._style


class QPushButton(QWidget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self.clicked = Signal()
        self._enabled = True
        self.minimum_height = None
        self._tooltip = ""

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def setMinimumHeight(self, value):
        self.minimum_height = value

    def setEnabled(self, value):
        self._enabled = bool(value)

    def isEnabled(self):
        return self._enabled

    def setToolTip(self, text):
        self._tooltip = text

    def toolTip(self):
        return self._tooltip

    def click(self):
        self.clicked.emit()


class QLineEdit(QWidget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text


class QCheckBox(QWidget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self._checked = False

    def setChecked(self, value):
        self._checked = bool(value)

    def isChecked(self):
        return self._checked


def pyqtSignal(*args, **kwargs):
    return Signal()


def load_dashboard(monkeypatch):
    pyqt6 = types.ModuleType("PyQt6")
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")
    qtcore = types.ModuleType("PyQt6.QtCore")

    qtwidgets.QWidget = QWidget
    qtwidgets.QVBoxLayout = QVBoxLayout
    qtwidgets.QHBoxLayout = QHBoxLayout
    qtwidgets.QGridLayout = QGridLayout
    qtwidgets.QGroupBox = QGroupBox
    qtwidgets.QLabel = QLabel
    qtwidgets.QPushButton = QPushButton
    qtwidgets.QLineEdit = QLineEdit
    qtwidgets.QCheckBox = QCheckBox
    qtcore.pyqtSignal = pyqtSignal

    monkeypatch.setitem(sys.modules, "PyQt6", pyqt6)
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", qtwidgets)
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", qtcore)

    sys.modules.pop("src.gui.dashboard", None)
    return importlib.import_module("src.gui.dashboard")


def test_dashboard_exposes_avp_panel_and_quick_actions(monkeypatch):
    dashboard = load_dashboard(monkeypatch)

    widget = dashboard.DashboardWidget()
    section_titles = [
        item[1].title()
        for item in widget._layout.items
        if item[0] == "widget" and hasattr(item[1], "title")
    ]

    assert widget.grp_overview.title() == "System Overview"
    assert section_titles[:5] == [
        "System Overview",
        "Quick Actions",
        "System Status",
        "Recommended Next Step",
        "AVP Details",
    ]
    assert widget.grp_avp.title() == "AVP Details"
    assert widget.btn_toggle_avp_details.text() == "Show AVP Details"
    assert widget.avp_details_panel.isVisible() is False
    assert widget.btn_retry_avp.text() == "Retry AVP"
    assert widget.btn_toggle_motor.text() == "Connect Motor"
    assert widget.btn_toggle_camera.text() == "Connect Camera"
    assert widget.btn_toggle_avp.text() == "Connect AVP"
    assert widget.btn_start_stream.text() == "Start Stream"
    assert widget.btn_toggle_tracking.text() == "Start Tracking"
    assert widget.btn_calibrate.text() == "Move To Home And Calibrate"
    assert widget.grp_guidance.title() == "Recommended Next Step"
    assert widget.btn_recovery_action.text() == "Connect AVP"


def test_dashboard_emits_split_action_signals(monkeypatch):
    dashboard = load_dashboard(monkeypatch)
    ui_state = importlib.import_module("src.gui.ui_state")

    widget = dashboard.DashboardWidget()
    emitted = []
    widget.connect_avp_requested.connect(lambda: emitted.append("connect_avp"))
    widget.disconnect_avp_requested.connect(lambda: emitted.append("disconnect_avp"))
    widget.retry_avp_requested.connect(lambda: emitted.append("retry_avp"))
    widget.connect_camera_requested.connect(lambda: emitted.append("connect_camera"))
    widget.disconnect_camera_requested.connect(lambda: emitted.append("disconnect_camera"))
    widget.connect_motor_requested.connect(lambda: emitted.append("connect_motor"))
    widget.disconnect_motor_requested.connect(lambda: emitted.append("disconnect_motor"))
    widget.start_stream_requested.connect(lambda: emitted.append("start_stream"))
    widget.stop_stream_requested.connect(lambda: emitted.append("stop_stream"))
    widget.toggle_tracking_requested.connect(lambda: emitted.append("toggle_tracking"))
    widget.calibrate_requested.connect(lambda: emitted.append("calibrate"))
    widget.recovery_action_requested.connect(lambda action: emitted.append(f"recovery:{action}"))

    widget.btn_toggle_motor.click()
    widget.btn_toggle_camera.click()
    widget.btn_toggle_avp.click()
    widget.btn_retry_avp.click()
    widget.btn_start_stream.click()
    widget.btn_toggle_tracking.click()
    widget.btn_calibrate.click()
    widget.btn_recovery_action.click()
    widget.update_system_snapshot(
        ui_state.SystemSnapshot(
            avp_connected=True,
            camera_connected=True,
            motor_connected=True,
            streaming=True,
            tracking=True,
            pose_sample_valid=True,
        )
    )
    widget.btn_toggle_motor.click()
    widget.btn_toggle_camera.click()
    widget.btn_toggle_avp.click()
    widget.btn_start_stream.click()
    widget.btn_toggle_tracking.click()
    widget.btn_recovery_action.click()

    assert emitted == [
        "connect_motor",
        "connect_camera",
        "connect_avp",
        "retry_avp",
        "start_stream",
        "toggle_tracking",
        "calibrate",
        "recovery:connect_avp",
        "disconnect_motor",
        "disconnect_camera",
        "disconnect_avp",
        "stop_stream",
        "toggle_tracking",
        "recovery:check_avp",
    ]


def test_dashboard_round_trips_manual_avp_settings(monkeypatch):
    dashboard = load_dashboard(monkeypatch)

    widget = dashboard.DashboardWidget()
    widget.set_avp_settings(ip="192.168.0.12", auto_reconnect=True)

    assert widget.get_avp_settings() == {
        "ip": "192.168.0.12",
        "auto_reconnect": True,
    }


def test_dashboard_updates_dynamic_action_labels_and_states(monkeypatch):
    dashboard = load_dashboard(monkeypatch)
    ui_state = importlib.import_module("src.gui.ui_state")

    widget = dashboard.DashboardWidget()

    widget.update_system_snapshot(
        ui_state.SystemSnapshot(
            avp_connected=False,
            camera_connected=False,
            motor_connected=False,
            streaming=False,
            tracking=False,
            pose_sample_valid=False,
            pose_sample_reason="idle",
        )
    )

    assert widget.btn_toggle_motor.text() == "Connect Motor"
    assert widget.btn_toggle_motor.isEnabled() is True
    assert widget.btn_toggle_avp.text() == "Connect AVP"
    assert widget.btn_toggle_avp.isEnabled() is True
    assert widget.btn_toggle_camera.text() == "Connect Camera"
    assert widget.btn_toggle_camera.isEnabled() is True
    assert widget.btn_start_stream.text() == "Start Stream"
    assert widget.btn_start_stream.isEnabled() is False
    assert "Connect AVP" in widget.btn_start_stream.toolTip()
    assert widget.btn_toggle_tracking.text() == "Start Tracking"
    assert widget.btn_toggle_tracking.isEnabled() is False
    assert "Connect AVP" in widget.btn_toggle_tracking.toolTip()
    assert widget.btn_calibrate.isEnabled() is False
    assert "Connect the neck motors first." == widget.btn_calibrate.toolTip()
    assert widget.label_recovery_title.text() == "AVP not connected"
    assert widget.label_recovery_detail.text() == "Use Quick Actions > Device Actions to connect AVP."
    assert widget.btn_recovery_action.text() == "Connect AVP"
    assert widget.btn_recovery_action.isEnabled() is False
    assert widget.btn_recovery_action.isVisible() is False
    assert "Blocked" in widget.label_badge.text()
    assert widget.grp_guidance.title() == "Recommended Next Step [Blocked]"

    widget.update_system_snapshot(
        ui_state.SystemSnapshot(
            avp_connected=True,
            camera_connected=True,
            motor_connected=True,
            streaming=True,
            tracking=True,
            pose_sample_valid=True,
            pose_sample_reason="ready",
        )
    )

    assert widget.btn_toggle_motor.text() == "Disconnect Motor"
    assert widget.btn_toggle_motor.isEnabled() is False
    assert widget.btn_toggle_avp.text() == "Disconnect AVP"
    assert widget.btn_toggle_avp.isEnabled() is False
    assert widget.btn_toggle_camera.text() == "Disconnect Camera"
    assert widget.btn_toggle_camera.isEnabled() is True
    assert widget.btn_start_stream.text() == "Stop Stream"
    assert widget.btn_start_stream.isEnabled() is True
    assert "Stop the active VisionPro stream" in widget.btn_start_stream.toolTip()
    assert widget.btn_toggle_tracking.text() == "Stop Tracking"
    assert widget.btn_toggle_tracking.isEnabled() is True
    assert "Stop neck tracking" in widget.btn_toggle_tracking.toolTip()
    assert widget.btn_calibrate.isEnabled() is False
    assert widget.label_recovery_title.text() == "System online"
    assert widget.btn_recovery_action.text() == "Check AVP"
    assert widget.btn_recovery_action.isVisible() is True
    assert "Ready" in widget.label_badge.text()
    assert widget.grp_guidance.title() == "Recommended Next Step [Ready]"
    assert widget.grp_guidance.set_title_calls == [
        "Recommended Next Step [Blocked]",
        "Recommended Next Step [Ready]",
    ]


def test_dashboard_recommends_camera_recovery_for_ready_pose_without_camera(monkeypatch):
    dashboard = load_dashboard(monkeypatch)
    ui_state = importlib.import_module("src.gui.ui_state")

    widget = dashboard.DashboardWidget()
    widget.update_system_snapshot(
        ui_state.SystemSnapshot(
            avp_connected=True,
            camera_connected=False,
            motor_connected=True,
            streaming=False,
            tracking=False,
            pose_sample_valid=True,
            pose_sample_reason="ready",
        )
    )

    assert widget.label_recovery_title.text() == "Camera required for stream"
    assert widget.label_recovery_detail.text() == "Use Quick Actions > Device Actions to connect the ZED camera."
    assert widget.btn_recovery_action.text() == "Connect Camera"
    assert widget.btn_recovery_action.isEnabled() is False
    assert widget.btn_recovery_action.isVisible() is False
    assert widget.grp_guidance.title() == "Recommended Next Step [Blocked]"
    assert widget.btn_calibrate.isEnabled() is True


def test_dashboard_avp_runtime_shows_pose_freshness_and_loop_stats(monkeypatch):
    dashboard = load_dashboard(monkeypatch)

    widget = dashboard.DashboardWidget()
    widget.update_avp_runtime(
        {"state": "ready", "ip": "172.20.10.2", "session_mode": "tracking_only", "last_error": None},
        pose_status={"reason": "stale_sample", "fresh": False},
        tracking_runtime={"pose_age_ms": 420.5, "loop_rate_hz": 58.2, "stale_pose_count": 3},
    )

    assert "State: ready | Mode: AVP Only | IP: 172.20.10.2" == widget.label_avp_runtime.text()
    assert "Pose: Not Fresh" in widget.label_avp_detail.text()
    assert "Reason: stale_sample" in widget.label_avp_detail.text()
    assert "Age: 420.5 ms" in widget.label_avp_detail.text()
    assert "Loop: 58.20 Hz" in widget.label_avp_detail.text()
    assert "Stale Count: 3" in widget.label_avp_detail.text()


def test_dashboard_marks_yaw_issue_as_warning(monkeypatch):
    dashboard = load_dashboard(monkeypatch)
    ui_state = importlib.import_module("src.gui.ui_state")

    widget = dashboard.DashboardWidget()
    widget.update_system_snapshot(
        ui_state.SystemSnapshot(
            avp_connected=True,
            camera_connected=True,
            motor_connected=True,
            streaming=False,
            tracking=False,
            pose_sample_valid=True,
            pose_sample_reason="ready",
            yaw_inactive=True,
        )
    )

    assert "Warning" in widget.label_badge.text()
    assert widget.grp_guidance.title() == "Recommended Next Step [Warning]"
    assert "Warning" in widget.label_severity.text()
    assert widget.btn_recovery_action.isVisible() is True
