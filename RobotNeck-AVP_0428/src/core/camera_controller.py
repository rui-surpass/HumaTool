import threading
import time

from config import config
from src.hardware.camera import (
    CameraInterface,
    _default_device_info,
    _default_health_status,
    _default_sensor_snapshot,
    _default_streaming_status,
)


def _clone_frame(frame):
    if hasattr(frame, "copy"):
        try:
            return frame.copy()
        except Exception:
            return frame
    return frame


class CameraController:
    """
    Independent lifecycle manager for the ZED camera.

    The controller now owns a single background capture loop. Callers read the
    latest cached frame instead of triggering hardware I/O directly.
    """

    def __init__(self):
        self.camera = None
        self.resolution = getattr(config, "STREAM_RESOLUTION", "1280x720")
        self.fps = config.STREAM_FPS
        self._capture_thread = None
        self._capture_stop_event = threading.Event()
        self._capture_lock = threading.Lock()
        self._latest_frame = None
        self._latest_frame_ok = False
        self._latest_frame_timestamp = None
        self._capture_stats = {
            "frames_captured": 0,
            "read_failures": 0,
            "consumer_reads": 0,
            "last_capture_timestamp": None,
            "capture_loop_rate_hz": 0.0,
            "last_error": "",
        }
        self._last_capture_timestamp = None

    @property
    def is_connected(self):
        return bool(self.camera and getattr(self.camera, "is_opened", False))

    def _camera_matches(self, resolution, fps):
        if not self.is_connected:
            return False

        try:
            width, height = map(int, resolution.split("x"))
        except Exception:
            return False

        return (
            getattr(self.camera, "width", None) == width
            and getattr(self.camera, "height", None) == height
            and getattr(self.camera, "fps", None) == fps
        )

    def open_camera(self, resolution=None, fps=None):
        self.resolution = resolution or self.resolution
        self.fps = fps or self.fps

        if self._camera_matches(self.resolution, self.fps):
            return self.camera

        if self.camera:
            self.close_camera()

        camera = CameraInterface(resolution=self.resolution, fps=self.fps)
        if not camera.is_opened:
            self.camera = None
            return None

        self.camera = camera
        self._reset_capture_state()
        self._capture_once()
        self._start_capture_worker()
        return self.camera

    def _reset_capture_state(self):
        with self._capture_lock:
            self._latest_frame = None
            self._latest_frame_ok = False
            self._latest_frame_timestamp = None
            self._capture_stats = {
                "frames_captured": 0,
                "read_failures": 0,
                "consumer_reads": 0,
                "last_capture_timestamp": None,
                "capture_loop_rate_hz": 0.0,
                "last_error": "",
            }
            self._last_capture_timestamp = None

    def _start_capture_worker(self):
        worker = self._capture_thread
        if worker and worker.is_alive():
            return

        self._capture_stop_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="camera-capture-loop",
            daemon=True,
        )
        self._capture_thread.start()

    def _capture_loop(self):
        interval_sec = 1.0 / max(1.0, float(self.fps or 1))
        while not self._capture_stop_event.is_set():
            self._capture_once()
            if self._capture_stop_event.wait(interval_sec):
                break

    def _capture_once(self):
        camera = self.camera
        if camera is None:
            return False

        try:
            ret, frame = camera.read()
        except Exception as exc:
            with self._capture_lock:
                self._latest_frame_ok = False
                self._capture_stats["read_failures"] += 1
                self._capture_stats["last_error"] = str(exc)
            return False

        now = time.time()
        with self._capture_lock:
            if ret and frame is not None:
                self._latest_frame = _clone_frame(frame)
                self._latest_frame_ok = True
                self._latest_frame_timestamp = now
                self._capture_stats["frames_captured"] += 1
                self._capture_stats["last_error"] = ""
            else:
                self._latest_frame_ok = False
                self._capture_stats["read_failures"] += 1

            self._capture_stats["last_capture_timestamp"] = now
            if self._last_capture_timestamp is not None and now > self._last_capture_timestamp:
                dt = now - self._last_capture_timestamp
                self._capture_stats["capture_loop_rate_hz"] = round(1.0 / dt, 3)
            self._last_capture_timestamp = now
        return bool(ret and frame is not None)

    def close_camera(self):
        self._capture_stop_event.set()
        worker = self._capture_thread
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=0.5)
        self._capture_thread = None

        if self.camera:
            self.camera.close()
            self.camera = None

        with self._capture_lock:
            self._latest_frame = None
            self._latest_frame_ok = False
            self._latest_frame_timestamp = None

    def get_frame_snapshot(self):
        with self._capture_lock:
            age_ms = None
            if self._latest_frame_timestamp is not None:
                age_ms = round(max(0.0, time.time() - self._latest_frame_timestamp) * 1000.0, 3)
            return {
                "ok": bool(self._latest_frame_ok),
                "frame": _clone_frame(self._latest_frame),
                "timestamp": self._latest_frame_timestamp,
                "age_ms": age_ms,
            }

    def get_capture_stats(self):
        with self._capture_lock:
            stats = dict(self._capture_stats)
            if self._latest_frame_timestamp is not None:
                stats["frame_age_ms"] = round(max(0.0, time.time() - self._latest_frame_timestamp) * 1000.0, 3)
            else:
                stats["frame_age_ms"] = None
            stats["thread_alive"] = bool(self._capture_thread and self._capture_thread.is_alive())
            return stats

    def get_latest_frame_age_ms(self):
        return self.get_capture_stats().get("frame_age_ms")

    def read(self):
        snapshot = self.get_frame_snapshot()
        with self._capture_lock:
            self._capture_stats["consumer_reads"] += 1
        return bool(snapshot["ok"]), snapshot["frame"]

    def get_imu_data(self):
        if self.camera:
            return self.camera.get_imu_data()
        return None

    def get_device_info(self):
        if self.camera:
            return self.camera.get_device_info()
        return _default_device_info(
            backend="unavailable",
            connected=False,
            sdk_available=False,
            model="Camera unavailable",
            serial_number="N/A",
            firmware_version="N/A",
            sensors_firmware_version="N/A",
            resolution=self.resolution,
            fps=self.fps,
            capabilities={
                "supports_manual_focus": False,
                "supports_auto_focus": False,
                "supports_depth_controls": False,
                "supports_sensor_snapshot": False,
                "supports_health_status": False,
                "supports_streaming": False,
            },
        )

    def get_sensor_snapshot(self):
        if self.camera:
            return self.camera.get_sensor_snapshot()
        return _default_sensor_snapshot("unavailable", False)

    def get_health_status(self):
        if self.camera:
            return self.camera.get_health_status()
        return _default_health_status("unavailable", False)

    def get_streaming_status(self):
        if self.camera:
            return self.camera.get_streaming_status()
        return _default_streaming_status("unavailable", False)

    def set_exposure(self, value):
        return bool(self.camera and self.camera.set_exposure(value))

    def set_whitebalance(self, value):
        return bool(self.camera and self.camera.set_whitebalance(value))

    def set_gain(self, value):
        return bool(self.camera and self.camera.set_gain(value))

    def set_auto_exposure(self, enabled):
        return bool(self.camera and self.camera.set_auto_exposure(enabled))

    def set_auto_whitebalance(self, enabled):
        return bool(self.camera and self.camera.set_auto_whitebalance(enabled))

    def set_confidence_threshold(self, value):
        return bool(self.camera and self.camera.set_confidence_threshold(value))

    def set_disparity_range(self, value):
        return bool(self.camera and self.camera.set_disparity_range(value))

    def set_view_mode(self, mode):
        return bool(self.camera and self.camera.set_view_mode(mode))

    def set_focus(self, value):
        return bool(self.camera and self.camera.set_focus(value))

    def set_auto_focus(self, enabled):
        if not self.camera:
            return False
        return self.camera.set_auto_focus(enabled)

    def enable_streaming(self, codec="H264", bitrate=8000, port=30000):
        return bool(self.camera and self.camera.enable_streaming(codec=codec, bitrate=bitrate, port=port))

    def disable_streaming(self):
        return bool(self.camera and self.camera.disable_streaming())
