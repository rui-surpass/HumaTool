import os
import sys
import types


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)


class Signal:
    def __init__(self, *args, **kwargs):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            try:
                callback(*args, **kwargs)
            except TypeError:
                callback()


class Widget:
    def __init__(self, *args, **kwargs):
        self._style = ""

    def setLayout(self, layout):
        self.layout = layout

    def setStyleSheet(self, style):
        self._style = style


class Layout:
    def __init__(self, *args, **kwargs):
        self.items = []

    def addWidget(self, widget, *args):
        self.items.append(("widget", widget, args))

    def addLayout(self, layout, *args):
        self.items.append(("layout", layout, args))


class QLabel(Widget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text

    def setText(self, text):
        self._text = text

    def setAlignment(self, value):
        self.alignment = value

    def setMinimumSize(self, *args):
        self.minimum_size = args


class QPushButton(Widget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self.clicked = Signal()

    def setText(self, text):
        self._text = text


class QComboBox(Widget):
    def __init__(self):
        super().__init__()
        self._items = []
        self._index = 0
        self.currentIndexChanged = Signal()

    def addItems(self, items):
        self._items.extend(items)

    def setToolTip(self, text):
        self.tooltip = text

    def setCurrentIndex(self, index):
        self._index = index
        self.currentIndexChanged.emit(index)

    def currentText(self):
        return self._items[self._index]

    def findText(self, text):
        try:
            return self._items.index(text)
        except ValueError:
            return -1


class QSlider(Widget):
    def __init__(self, *args):
        super().__init__()
        self._value = 0
        self.valueChanged = Signal()
        self.sliderReleased = Signal()

    def setRange(self, low, high):
        self.range = (low, high)

    def setValue(self, value):
        self._value = value
        self.valueChanged.emit(value)

    def value(self):
        return self._value

    def setSingleStep(self, value):
        self.single_step = value


class QCheckBox(Widget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self.toggled = Signal()


class QMessageBox:
    class StandardButton:
        Yes = 1
        No = 2

    @staticmethod
    def question(*args, **kwargs):
        return QMessageBox.StandardButton.No


qtwidgets = types.SimpleNamespace(
    QWidget=Widget,
    QGroupBox=Widget,
    QVBoxLayout=Layout,
    QGridLayout=Layout,
    QLabel=QLabel,
    QComboBox=QComboBox,
    QSlider=QSlider,
    QCheckBox=QCheckBox,
    QPushButton=QPushButton,
    QHBoxLayout=Layout,
    QMessageBox=QMessageBox,
)
qtcore = types.SimpleNamespace(
    Qt=types.SimpleNamespace(Orientation=types.SimpleNamespace(Horizontal=1), AlignmentFlag=types.SimpleNamespace(AlignCenter=1)),
    pyqtSignal=Signal,
    QTimer=object,
)
qtgui = types.SimpleNamespace(QImage=object, QPixmap=object, QColor=object)
sys.modules.setdefault("PyQt6", types.SimpleNamespace())
sys.modules.setdefault("PyQt6.QtWidgets", qtwidgets)
sys.modules.setdefault("PyQt6.QtCore", qtcore)
sys.modules.setdefault("PyQt6.QtGui", qtgui)

from src.gui.teleop_stream import TeleopStreamWidget


def test_teleop_stream_defaults_to_1080p30_with_stable_bitrate():
    widget = TeleopStreamWidget()

    resolution, fps, bitrate, stereo, latency = widget.get_config()

    assert resolution == "3840x1080"
    assert fps == 30
    assert bitrate == 12000
    assert stereo is True
    assert latency == "Low Latency"


def test_teleop_stream_reset_defaults_restores_stable_bitrate():
    widget = TeleopStreamWidget()
    widget.slider_bitrate.setValue(30000)

    widget.reset_defaults()

    assert widget.get_config()[2] == 12000
