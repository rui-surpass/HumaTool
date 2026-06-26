import os
import sys
import time


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.core.camera_controller import CameraController


class FakeCamera:
    def __init__(self, resolution, fps):
        self.width, self.height = map(int, resolution.split("x"))
        self.fps = fps
        self.resolution = resolution
        self.is_opened = True
        self.closed = False
        self.read_calls = 0

    def close(self):
        self.closed = True
        self.is_opened = False

    def read(self):
        self.read_calls += 1
        return True, f"frame-{self.read_calls}"

    def get_imu_data(self):
        return (1.0, 2.0, 3.0)

    def get_device_info(self):
        return {"connected": True, "backend": "fake"}

    def get_sensor_snapshot(self):
        return {"imu": {"available": True}}

    def get_health_status(self):
        return {"supported": True}

    def get_streaming_status(self):
        return {"enabled": False}

    def enable_streaming(self, codec="H264", bitrate=8000, port=30000):
        self.last_stream = (codec, bitrate, port)
        return True

    def disable_streaming(self):
        self.stream_disabled = True
        return True


def test_open_camera_reuses_existing_camera_when_configuration_matches(monkeypatch):
    created = []

    def fake_camera_interface(resolution, fps):
        camera = FakeCamera(resolution, fps)
        created.append(camera)
        return camera

    monkeypatch.setattr("src.core.camera_controller.CameraInterface", fake_camera_interface)

    controller = CameraController()

    first = controller.open_camera("3840x1080", 30)
    second = controller.open_camera("3840x1080", 30)

    assert first is second
    assert len(created) == 1


def test_open_camera_reopens_when_configuration_changes(monkeypatch):
    created = []

    def fake_camera_interface(resolution, fps):
        camera = FakeCamera(resolution, fps)
        created.append(camera)
        return camera

    monkeypatch.setattr("src.core.camera_controller.CameraInterface", fake_camera_interface)

    controller = CameraController()

    first = controller.open_camera("3840x1080", 30)
    second = controller.open_camera("2560x720", 60)

    assert first is not second
    assert first.closed is True
    assert len(created) == 2


def test_camera_controller_delegates_runtime_methods(monkeypatch):
    monkeypatch.setattr(
        "src.core.camera_controller.CameraInterface",
        lambda resolution, fps: FakeCamera(resolution, fps),
    )

    controller = CameraController()
    controller.open_camera("3840x1080", 30)

    ret, frame = controller.read()
    assert ret is True
    assert str(frame).startswith("frame-")
    assert controller.get_imu_data() == (1.0, 2.0, 3.0)
    assert controller.get_device_info()["backend"] == "fake"
    assert controller.enable_streaming("H265", 12000, 31000) is True
    assert controller.disable_streaming() is True


def test_camera_controller_reads_from_cached_frame_after_background_capture(monkeypatch):
    created = []

    def fake_camera_interface(resolution, fps):
        camera = FakeCamera(resolution, fps)
        created.append(camera)
        return camera

    monkeypatch.setattr("src.core.camera_controller.CameraInterface", fake_camera_interface)

    controller = CameraController()
    controller.open_camera("3840x1080", 30)

    deadline = time.time() + 0.2
    while created[0].read_calls == 0 and time.time() < deadline:
        time.sleep(0.01)

    first = controller.read()
    second = controller.read()
    stats = controller.get_capture_stats()

    assert first == second
    assert created[0].read_calls >= 1
    assert stats["frames_captured"] >= 1
    assert stats["consumer_reads"] >= 2


def test_camera_controller_exposes_latest_frame_snapshot(monkeypatch):
    monkeypatch.setattr(
        "src.core.camera_controller.CameraInterface",
        lambda resolution, fps: FakeCamera(resolution, fps),
    )

    controller = CameraController()
    controller.open_camera("3840x1080", 30)

    deadline = time.time() + 0.2
    snapshot = None
    while time.time() < deadline:
        snapshot = controller.get_frame_snapshot()
        if snapshot["ok"]:
            break
        time.sleep(0.01)

    assert snapshot["ok"] is True
    assert snapshot["frame"] is not None
    assert snapshot["age_ms"] is not None
