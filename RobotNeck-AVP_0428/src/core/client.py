from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from avp_stream.streamer import VisionProStreamer
    VISION_PRO_STREAMER_IMPORT_ERROR = ""
except ImportError as exc:
    VisionProStreamer = None
    VISION_PRO_STREAMER_IMPORT_ERROR = str(exc)

from config import config
from src.core.timing_debug import RuntimeTimingTracker, timing_debug_enabled
from src.utils.orientation import extract_avp_head_euler


logger = logging.getLogger(__name__)


AVP_RECONNECT_RETRY_SEC = 1.0
AVP_RECOVERY_TIMEOUT_SEC = max(1.0, float(getattr(config, "AVP_TIMEOUT_SEC", 0.25)) * 4.0)


@dataclass
class HeadPoseSample:
    head_pose_matrix: np.ndarray
    timestamp: float
    monotonic_timestamp: float
    base_imu_rpy: tuple | None
    raw_payload: dict
    fresh: bool
    source_timestamp: float | None = None


class AVPClient:
    """
    Manual-connect AVP client with optional background reconnect.
    """

    def __init__(self, ip):
        self.ip = str(ip)
        self.session_mode = "tracking_only"
        self.streamer = None
        self.running = False
        self.using_dummy_video = False
        self.frame_source = None
        self.stream_resolution = getattr(config, "STREAM_RESOLUTION", "1280x720")
        self.stream_fps = getattr(config, "STREAM_FPS", 30)
        self.stream_bitrate = 8192

        self._streamer_lock = threading.Lock()
        self._streamer_thread = None
        self._streamer_error = None
        self._streamer_import_error = VISION_PRO_STREAMER_IMPORT_ERROR
        self._connect_requested = False
        self._auto_reconnect = False
        self._stop_event = threading.Event()
        self._last_sample_timestamp = None
        self._last_head_matrix = None
        self._has_ever_received_pose = False
        self._last_pose_status = {
            "valid": False,
            "reason": "idle",
            "fresh": False,
            "last_sample_timestamp": None,
            "last_sample_monotonic": None,
            "last_sample_wall_time": None,
            "age_ms": None,
            "source_timestamp": None,
            "last_matrix_shape": None,
            "error": None,
            "state_since_monotonic": time.monotonic(),
        }
        self._connection_status = {
            "state": "idle",
            "ip": self.ip,
            "auto_reconnect": False,
            "session_mode": self.session_mode,
            "last_error": None,
            "state_since_monotonic": time.monotonic(),
            "last_sample_timestamp": None,
            "has_ever_received_pose": False,
        }
        self._timing_debug_enabled = timing_debug_enabled()
        self._avp_read_timing = RuntimeTimingTracker(
            "avp_get_latest",
            enabled=self._timing_debug_enabled,
            log_every_sec=5.0,
            slow_threshold_ms=20.0,
        )
        self._video_callback_timing = RuntimeTimingTracker(
            "video_frame_callback",
            enabled=self._timing_debug_enabled,
            log_every_sec=5.0,
            slow_threshold_ms=20.0,
        )
        self._stale_transition_count = 0
        self._fresh_transition_count = 0
        self._repeated_head_matrix_count = 0
        self._repeated_source_timestamp_count = 0
        self._last_fresh_state = None
        self._last_source_timestamp = None
        self._last_receive_monotonic = None
        self._last_unique_sample_monotonic = None
        self._receive_rate_hz = 0.0
        self._source_update_rate_hz = 0.0
        self._sample_sequence = 0

    def connect(self, ip=None, auto_reconnect=False, session_mode="tracking_only"):
        self._ensure_runtime_fields()
        if ip:
            self.ip = str(ip)
        self.session_mode = str(session_mode or "tracking_only")

        self._connect_requested = True
        self._auto_reconnect = bool(auto_reconnect)
        self._stop_event.clear()

        start_streamer_method = getattr(self, "_start_streamer_thread", None)
        start_streamer_func = getattr(start_streamer_method, "__func__", None)
        streamer_start_is_stubbed = callable(start_streamer_method) and (
            start_streamer_func is None or start_streamer_func is not AVPClient._start_streamer_thread
        )
        if VisionProStreamer is None and not streamer_start_is_stubbed:
            self._streamer_import_error = self._streamer_import_error or "VisionProStreamer import failed."
            self._set_connection_state("error", error=self._streamer_import_error)
            self._set_pose_status(
                valid=False,
                reason="streamer_import_failed",
                fresh=False,
                error=self._streamer_import_error,
            )
            self._connect_requested = False
            return False

        if self.streamer is not None:
            state = "ready" if self._has_ever_received_pose else "connected_waiting_first_sample"
            self._set_connection_state(state)
            return True

        if self._streamer_thread and self._streamer_thread.is_alive():
            self._set_connection_state("reconnecting" if self._auto_reconnect else "connecting")
            return True

        self._set_connection_state("connecting")
        self._set_pose_status(valid=False, reason="streamer_initializing", fresh=False)
        self._start_streamer_thread()
        return True

    def disconnect(self):
        self._ensure_runtime_fields()
        self._connect_requested = False
        self._auto_reconnect = False
        self._stop_event.set()
        self._cleanup_streamer()

        worker = self._streamer_thread
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=0.2)
        if self._streamer_thread is worker:
            self._streamer_thread = None

        self._set_connection_state("disconnected")
        self._set_pose_status(valid=False, reason="disconnected", fresh=False)

    def retry_now(self):
        self._ensure_runtime_fields()
        if not self.ip:
            return False

        self._connect_requested = True
        self._stop_event.clear()
        self._cleanup_streamer()
        self._set_connection_state("reconnecting")
        self._set_pose_status(valid=False, reason="streamer_initializing", fresh=False)
        self._start_streamer_thread()
        return True

    def get_connection_status(self):
        self._ensure_runtime_fields()
        status = dict(self._connection_status)
        state_since = status.get("state_since_monotonic")
        status["state_age_sec"] = round(max(0.0, time.monotonic() - state_since), 6) if state_since is not None else 0.0
        return status

    def get_pose_status(self):
        self._ensure_runtime_fields()
        status = dict(self._last_pose_status)
        reason = status.get("reason", "idle")

        if reason in {"idle", "disconnected"}:
            pass
        elif self._streamer_import_error and self.streamer is None:
            status["reason"] = "streamer_import_failed"
            status["error"] = self._streamer_import_error
        elif self.streamer is None:
            if self._streamer_thread is not None and self._streamer_thread.is_alive():
                status["reason"] = "streamer_initializing"
            elif self._streamer_error is not None:
                status["reason"] = "streamer_init_failed"
                status["error"] = str(self._streamer_error)
            elif self._connect_requested:
                status["reason"] = "streamer_initializing"
        elif not self._has_ever_received_pose and status.get("reason") in {
            "",
            "uninitialized",
            "streamer_not_ready",
            "streamer_initializing",
            "idle",
            "disconnected",
            "stream_established_waiting_first_sample",
        }:
            status["reason"] = "stream_established_waiting_first_sample"

        state_since = status.get("state_since_monotonic")
        status["state_age_sec"] = round(max(0.0, time.monotonic() - state_since), 6) if state_since is not None else 0.0
        return status

    def get_camera_imu(self):
        frame_source = getattr(self, "frame_source", None)
        if frame_source and hasattr(frame_source, "get_imu_data"):
            return frame_source.get_imu_data()
        return None

    def start_video_stream(
        self,
        frame_source=None,
        resolution=None,
        fps=None,
        bitrate=None,
        stereo=True,
        latency="Balanced",
    ):
        self._ensure_runtime_fields()
        if not config.ENABLE_VIDEO:
            logger.warning("Video streaming disabled in config.")
            return False

        if resolution:
            self.stream_resolution = resolution
        if fps:
            self.stream_fps = fps
        if bitrate:
            self.stream_bitrate = bitrate

        self.frame_source = frame_source
        self.using_dummy_video = self.frame_source is None
        if self.frame_source is None and not getattr(config, "USE_DUMMY_VIDEO_IF_NO_CAMERA", False):
            return False

        if self.streamer is None:
            logger.error("Streamer is not initialized. Cannot configure video.")
            return False

        self.streamer.configure_video(
            device=None,
            size=self.stream_resolution,
            fps=self.stream_fps,
            stereo=stereo,
            bitrate=self.stream_bitrate,
        )
        self.streamer.register_frame_callback(self._video_callback)
        self.streamer.start_webrtc(port=9999)
        self.session_mode = "streaming"
        self._set_connection_state(self._connection_status.get("state", "ready"))
        logger.info("Configuring WebRTC video: latency=%s, resolution=%s, fps=%s", latency, self.stream_resolution, self.stream_fps)
        logger.info("WebRTC stream started on port 9999.")
        return True

    def stop_video_stream(self, close_camera=False):
        self._ensure_runtime_fields()
        self._cleanup_streamer()
        self.frame_source = None
        self.using_dummy_video = False
        self.session_mode = "tracking_only"
        self._set_connection_state(self._connection_status.get("state", "idle"))
        return True

    def restart_video_stream(
        self,
        frame_source=None,
        resolution=None,
        fps=None,
        bitrate=None,
        stereo=True,
        latency="Balanced",
    ):
        logger.info(
            "Restarting stream: resolution=%s fps=%s bitrate=%s stereo=%s latency=%s",
            resolution,
            fps,
            bitrate,
            stereo,
            latency,
        )
        self.stop_video_stream(close_camera=False)
        time.sleep(1.0)
        return self.start_video_stream(
            frame_source=frame_source,
            resolution=resolution,
            fps=fps,
            bitrate=bitrate,
            stereo=stereo,
            latency=latency,
        )

    def get_latest_head_pose_sample(self, now=None):
        self._ensure_runtime_fields()
        if now is None:
            now = time.monotonic()

        if self.streamer is None:
            return self._handle_missing_streamer(now)

        read_started = time.perf_counter()
        try:
            data = self.streamer.get_latest()
        except Exception as exc:
            self._avp_read_timing.record(
                (time.perf_counter() - read_started) * 1000.0,
                now=time.time(),
                extra={"status": "read_failed"},
            )
            self._streamer_error = exc
            self._set_pose_status(valid=False, reason="streamer_read_failed", fresh=False, error=str(exc))
            if self._connect_requested and self._auto_reconnect:
                self._schedule_reconnect("streamer_read_failed")
            return None

        if not data:
            return self._handle_empty_payload(now)

        if "head" not in data:
            self._set_pose_status(valid=False, reason="missing_head_field", fresh=False)
            return None

        head_mat = np.asarray(data["head"])
        if head_mat.ndim == 3:
            head_mat = head_mat[0]

        if head_mat.shape != (4, 4):
            self._set_pose_status(
                valid=False,
                reason="invalid_head_shape",
                fresh=False,
                last_matrix_shape=tuple(head_mat.shape),
            )
            return None

        if not np.isfinite(head_mat).all():
            self._set_pose_status(valid=False, reason="invalid_head_values", fresh=False)
            return None

        source_timestamp = data.get("timestamp")
        receive_monotonic = now
        sample_wall_time = time.time()
        if isinstance(source_timestamp, (int, float)):
            sample_wall_time = float(source_timestamp)

        if self._last_receive_monotonic is not None and now > self._last_receive_monotonic:
            self._receive_rate_hz = round(1.0 / max(1e-9, now - self._last_receive_monotonic), 3)
        self._last_receive_monotonic = now

        previous_source_timestamp = self._last_source_timestamp
        source_changed = (
            isinstance(source_timestamp, (int, float))
            and source_timestamp != previous_source_timestamp
        )
        matrix_changed = self._last_head_matrix is None or not np.array_equal(self._last_head_matrix, head_mat)
        unique_sample = self._last_head_matrix is None or source_changed or matrix_changed
        if unique_sample:
            if self._last_unique_sample_monotonic is not None and now > self._last_unique_sample_monotonic:
                self._source_update_rate_hz = round(1.0 / max(1e-9, now - self._last_unique_sample_monotonic), 3)
            self._last_unique_sample_monotonic = now
            self._sample_sequence += 1
        sample_monotonic = self._last_unique_sample_monotonic if self._last_unique_sample_monotonic is not None else now

        sample_age_sec = max(0.0, now - sample_monotonic)
        fresh = sample_age_sec <= float(getattr(config, "AVP_TIMEOUT_SEC", 0.25))

        sample = HeadPoseSample(
            head_pose_matrix=head_mat,
            timestamp=sample_wall_time,
            monotonic_timestamp=sample_monotonic,
            base_imu_rpy=self.get_camera_imu(),
            raw_payload={
                **data,
                "fresh": fresh,
                "source_timestamp": source_timestamp,
                "sample_monotonic_timestamp": sample_monotonic,
                "receive_monotonic_timestamp": receive_monotonic,
                "sample_wall_time": sample_wall_time,
                "sample_sequence": self._sample_sequence,
                "unique_sample": bool(unique_sample),
            },
            fresh=fresh,
            source_timestamp=source_timestamp,
        )

        age_ms = round(sample_age_sec * 1000.0, 3)

        if self._last_head_matrix is not None and np.array_equal(self._last_head_matrix, head_mat):
            self._repeated_head_matrix_count += 1
        else:
            self._repeated_head_matrix_count = 0
        if isinstance(source_timestamp, (int, float)) and source_timestamp == self._last_source_timestamp:
            self._repeated_source_timestamp_count += 1
        else:
            self._repeated_source_timestamp_count = 0
        self._last_source_timestamp = source_timestamp if isinstance(source_timestamp, (int, float)) else previous_source_timestamp

        if self._last_fresh_state is not None and self._last_fresh_state != fresh:
            if fresh:
                self._fresh_transition_count += 1
            else:
                self._stale_transition_count += 1
        self._last_fresh_state = bool(fresh)

        self._last_head_matrix = head_mat
        self._last_sample_timestamp = sample_monotonic
        self._has_ever_received_pose = True
        self._set_connection_state("ready")
        self._set_pose_status(
            valid=True,
            reason="ready" if fresh else "stale_sample",
            fresh=fresh,
            last_sample_timestamp=sample_monotonic,
            last_sample_monotonic=sample_monotonic,
            last_sample_wall_time=sample_wall_time,
            age_ms=age_ms,
            source_timestamp=source_timestamp,
            last_matrix_shape=tuple(head_mat.shape),
            repeated_head_matrix_count=int(self._repeated_head_matrix_count),
            repeated_source_timestamp_count=int(self._repeated_source_timestamp_count),
            sample_sequence=int(self._sample_sequence),
            receive_rate_hz=float(self._receive_rate_hz),
            source_update_rate_hz=float(self._source_update_rate_hz),
        )
        self._avp_read_timing.record(
            (time.perf_counter() - read_started) * 1000.0,
            now=time.time(),
            extra={
                "fresh": bool(fresh),
                "age_ms": age_ms if age_ms is not None else "na",
                "repeated": int(self._repeated_head_matrix_count),
                "sequence": int(self._sample_sequence),
                "stale_transitions": int(self._stale_transition_count),
            },
        )

        if (
            not fresh
            and self._connect_requested
            and self._auto_reconnect
            and now - sample_monotonic > AVP_RECOVERY_TIMEOUT_SEC
        ):
            self._schedule_reconnect("stale_sample")
        return sample

    def get_latest_head_pose(self):
        matrix = self.get_latest_head_pose_matrix()
        if matrix is None:
            return None

        try:
            yaw, pitch, roll = extract_avp_head_euler(matrix[:3, :3])
            return yaw, pitch, roll
        except Exception:
            return None

    def get_latest_head_pose_matrix(self, now=None, allow_cached=False):
        sample = self.get_latest_head_pose_sample(now=now)
        if sample is not None and bool(sample.fresh):
            return sample.head_pose_matrix
        if allow_cached:
            status = self.get_pose_status()
            if bool(status.get("fresh", False)):
                return self._last_head_matrix
        return None

    def _video_callback(self, blank_frame):
        self._ensure_runtime_fields()
        callback_started = time.perf_counter()
        if getattr(self, "using_dummy_video", False):
            res = getattr(config, "STREAM_RESOLUTION", "1280x720")
            target_w, target_h = map(int, res.split("x"))
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            if cv2 is None:
                return frame

            t = time.time()
            shift = int(t * 100) % target_w
            frame[:, : target_w // 2, 2] = (np.arange(target_w // 2) + shift) % 255
            frame[:, target_w // 2 :, 0] = (np.arange(target_w // 2) + shift) % 255
            cv2.putText(frame, "TEST PATTERN - LEFT", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(
                frame,
                "TEST PATTERN - RIGHT",
                (target_w // 2 + 50, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 255, 255),
                2,
            )
            cv2.putText(frame, f"Time: {t:.2f}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            self._video_callback_timing.record(
                (time.perf_counter() - callback_started) * 1000.0,
                now=time.time(),
                extra={"source": "dummy"},
            )
            return frame

        if getattr(self, "frame_source", None):
            ret, frame = self.frame_source.read()
            if ret:
                self._video_callback_timing.record(
                    (time.perf_counter() - callback_started) * 1000.0,
                    now=time.time(),
                    extra={"source": "camera", "success": True},
                )
                return frame
        self._video_callback_timing.record(
            (time.perf_counter() - callback_started) * 1000.0,
            now=time.time(),
            extra={"source": "blank", "success": False},
        )
        return blank_frame

    def get_debug_timing_snapshot(self):
        self._ensure_runtime_fields()
        return {
            "avp_read": self._avp_read_timing.snapshot(),
            "video_callback": self._video_callback_timing.snapshot(),
            "fresh_transition_count": int(getattr(self, "_fresh_transition_count", 0)),
            "stale_transition_count": int(getattr(self, "_stale_transition_count", 0)),
            "repeated_head_matrix_count": int(getattr(self, "_repeated_head_matrix_count", 0)),
            "repeated_source_timestamp_count": int(getattr(self, "_repeated_source_timestamp_count", 0)),
            "source_update_rate_hz": float(getattr(self, "_source_update_rate_hz", 0.0)),
            "receive_rate_hz": float(getattr(self, "_receive_rate_hz", 0.0)),
            "sample_sequence": int(getattr(self, "_sample_sequence", 0)),
        }

    def close(self):
        self.disconnect()

    def _handle_missing_streamer(self, now):
        if self._streamer_import_error:
            self._set_pose_status(
                valid=False,
                reason="streamer_import_failed",
                fresh=False,
                error=self._streamer_import_error,
            )
            return None

        if self._streamer_thread is not None and self._streamer_thread.is_alive():
            self._set_pose_status(valid=False, reason="streamer_initializing", fresh=False)
            return None

        if self._streamer_error is not None:
            self._set_pose_status(
                valid=False,
                reason="streamer_init_failed",
                fresh=False,
                error=str(self._streamer_error),
            )
            return None

        self._set_pose_status(valid=False, reason="idle" if not self._connect_requested else "streamer_initializing", fresh=False)
        return None

    def _handle_empty_payload(self, now):
        if not self._has_ever_received_pose:
            self._set_connection_state("connected_waiting_first_sample")
            self._set_pose_status(valid=False, reason="stream_established_waiting_first_sample", fresh=False)
            status = self.get_connection_status()
            if self._connect_requested and self._auto_reconnect and status["state_age_sec"] > AVP_RECOVERY_TIMEOUT_SEC:
                self._schedule_reconnect("waiting_for_first_sample")
            return None

        last_timestamp = self._last_sample_timestamp
        if last_timestamp is None:
            self._set_pose_status(valid=False, reason="sample_missing", fresh=False)
            return None

        age_sec = max(0.0, now - last_timestamp)
        reason = "stale_sample" if age_sec > float(getattr(config, "AVP_TIMEOUT_SEC", 0.25)) else "sample_missing"
        self._set_pose_status(
            valid=False,
            reason=reason,
            fresh=False,
            last_sample_timestamp=last_timestamp,
            last_sample_monotonic=last_timestamp,
            age_ms=round(max(0.0, age_sec) * 1000.0, 3),
        )
        if self._connect_requested and self._auto_reconnect and age_sec > AVP_RECOVERY_TIMEOUT_SEC:
            self._schedule_reconnect(reason)
        return None

    def _start_streamer_thread(self):
        if self._streamer_thread and self._streamer_thread.is_alive():
            return
        self._streamer_thread = threading.Thread(
            target=self._connect_streamer_worker,
            name="avp-streamer-connect",
            daemon=True,
        )
        self._streamer_thread.start()

    def _connect_streamer_worker(self):
        try:
            while self._connect_requested and not self._stop_event.is_set():
                try:
                    streamer = VisionProStreamer(ip=self.ip, record=True)
                    if self._stop_event.is_set() or not self._connect_requested:
                        if hasattr(streamer, "cleanup"):
                            streamer.cleanup()
                        return
                    with self._streamer_lock:
                        self.streamer = streamer
                    self._streamer_error = None
                    self._set_connection_state("connected_waiting_first_sample")
                    self._set_pose_status(valid=False, reason="stream_established_waiting_first_sample", fresh=False)
                    return
                except Exception as exc:
                    self._streamer_error = exc
                    if not self._auto_reconnect:
                        self._connect_requested = False
                        self._set_connection_state("error", error=str(exc))
                        self._set_pose_status(valid=False, reason="streamer_init_failed", fresh=False, error=str(exc))
                        return
                    self._set_connection_state("reconnecting", error=str(exc))
                    self._set_pose_status(valid=False, reason="streamer_initializing", fresh=False, error=str(exc))
                    if self._stop_event.wait(AVP_RECONNECT_RETRY_SEC):
                        return
        finally:
            self._streamer_thread = None

    def _schedule_reconnect(self, error_reason):
        if not self._connect_requested or not self._auto_reconnect:
            return

        self._cleanup_streamer()
        self._set_connection_state("reconnecting", error=error_reason)
        self._set_pose_status(valid=False, reason="streamer_initializing", fresh=False, error=error_reason)
        self._start_streamer_thread()

    def _cleanup_streamer(self):
        lock = getattr(self, "_streamer_lock", None)
        if lock is None:
            streamer = self.streamer
            self.streamer = None
        else:
            with lock:
                streamer = self.streamer
                self.streamer = None
        if streamer and hasattr(streamer, "cleanup"):
            try:
                streamer.cleanup()
            except Exception:
                pass

    def _set_connection_state(self, state, error=None):
        current = getattr(self, "_connection_status", {})
        now = time.monotonic()
        payload = dict(current)
        payload["state"] = state
        payload["ip"] = getattr(self, "ip", payload.get("ip", ""))
        payload["auto_reconnect"] = bool(getattr(self, "_auto_reconnect", payload.get("auto_reconnect", False)))
        payload["session_mode"] = getattr(self, "session_mode", payload.get("session_mode", "tracking_only"))
        payload["last_error"] = error if error is not None else payload.get("last_error")
        payload["last_sample_timestamp"] = getattr(self, "_last_sample_timestamp", payload.get("last_sample_timestamp"))
        payload["has_ever_received_pose"] = bool(getattr(self, "_has_ever_received_pose", payload.get("has_ever_received_pose", False)))
        if current.get("state") != state:
            payload["state_since_monotonic"] = now
        else:
            payload["state_since_monotonic"] = payload.get("state_since_monotonic", now)
        if error is None and state in {"idle", "connecting", "connected_waiting_first_sample", "ready", "reconnecting", "disconnected"}:
            payload["last_error"] = None
        self._connection_status = payload

    def _set_pose_status(
        self,
        valid,
        reason,
        fresh,
        error=None,
        last_sample_timestamp=None,
        last_sample_monotonic=None,
        last_sample_wall_time=None,
        age_ms=None,
        source_timestamp=None,
        last_matrix_shape=None,
        repeated_head_matrix_count=None,
        repeated_source_timestamp_count=None,
        sample_sequence=None,
        receive_rate_hz=None,
        source_update_rate_hz=None,
    ):
        current = getattr(self, "_last_pose_status", {})
        now = time.monotonic()
        payload = dict(current)
        payload["valid"] = bool(valid)
        payload["reason"] = reason
        payload["fresh"] = bool(fresh)
        payload["error"] = error
        payload["last_sample_timestamp"] = last_sample_timestamp
        payload["last_sample_monotonic"] = last_sample_monotonic
        payload["last_sample_wall_time"] = last_sample_wall_time
        payload["age_ms"] = age_ms
        payload["source_timestamp"] = source_timestamp
        payload["last_matrix_shape"] = last_matrix_shape
        payload["repeated_head_matrix_count"] = repeated_head_matrix_count
        payload["repeated_source_timestamp_count"] = repeated_source_timestamp_count
        payload["sample_sequence"] = sample_sequence
        payload["receive_rate_hz"] = receive_rate_hz
        payload["source_update_rate_hz"] = source_update_rate_hz
        if current.get("reason") != reason or current.get("valid") != bool(valid):
            payload["state_since_monotonic"] = now
        else:
            payload["state_since_monotonic"] = payload.get("state_since_monotonic", now)
        self._last_pose_status = payload

    def _ensure_runtime_fields(self):
        if not hasattr(self, "_streamer_lock"):
            self._streamer_lock = threading.Lock()
        if not hasattr(self, "_streamer_thread"):
            self._streamer_thread = None
        if not hasattr(self, "_streamer_error"):
            self._streamer_error = None
        if not hasattr(self, "_streamer_import_error"):
            self._streamer_import_error = VISION_PRO_STREAMER_IMPORT_ERROR
        if not hasattr(self, "_connect_requested"):
            self._connect_requested = False
        if not hasattr(self, "_auto_reconnect"):
            self._auto_reconnect = False
        if not hasattr(self, "_stop_event"):
            self._stop_event = threading.Event()
        if not hasattr(self, "_last_sample_timestamp"):
            self._last_sample_timestamp = None
        if not hasattr(self, "_last_head_matrix"):
            self._last_head_matrix = None
        if not hasattr(self, "_has_ever_received_pose"):
            self._has_ever_received_pose = False
        if not hasattr(self, "_last_pose_status"):
            self._last_pose_status = {
                "valid": False,
                "reason": "idle",
                "fresh": False,
                "last_sample_timestamp": None,
                "last_sample_monotonic": None,
                "last_sample_wall_time": None,
                "age_ms": None,
                "source_timestamp": None,
                "last_matrix_shape": None,
                "error": None,
                "state_since_monotonic": time.monotonic(),
            }
        if not hasattr(self, "_connection_status"):
            self._connection_status = {
                "state": "idle",
                "ip": getattr(self, "ip", ""),
                "auto_reconnect": False,
                "session_mode": getattr(self, "session_mode", "tracking_only"),
                "last_error": None,
                "state_since_monotonic": time.monotonic(),
                "last_sample_timestamp": None,
                "has_ever_received_pose": False,
            }
        if not hasattr(self, "session_mode"):
            self.session_mode = self._connection_status.get("session_mode", "tracking_only")
        if not hasattr(self, "_timing_debug_enabled"):
            self._timing_debug_enabled = timing_debug_enabled()
        if not hasattr(self, "_avp_read_timing"):
            self._avp_read_timing = RuntimeTimingTracker(
                "avp_get_latest",
                enabled=self._timing_debug_enabled,
                log_every_sec=5.0,
                slow_threshold_ms=20.0,
            )
        if not hasattr(self, "_video_callback_timing"):
            self._video_callback_timing = RuntimeTimingTracker(
                "video_frame_callback",
                enabled=self._timing_debug_enabled,
                log_every_sec=5.0,
                slow_threshold_ms=20.0,
            )
        if not hasattr(self, "_stale_transition_count"):
            self._stale_transition_count = 0
        if not hasattr(self, "_fresh_transition_count"):
            self._fresh_transition_count = 0
        if not hasattr(self, "_repeated_head_matrix_count"):
            self._repeated_head_matrix_count = 0
        if not hasattr(self, "_repeated_source_timestamp_count"):
            self._repeated_source_timestamp_count = 0
        if not hasattr(self, "_last_fresh_state"):
            self._last_fresh_state = None
        if not hasattr(self, "_last_source_timestamp"):
            self._last_source_timestamp = None
        if not hasattr(self, "_last_receive_monotonic"):
            self._last_receive_monotonic = None
        if not hasattr(self, "_last_unique_sample_monotonic"):
            self._last_unique_sample_monotonic = None
        if not hasattr(self, "_receive_rate_hz"):
            self._receive_rate_hz = 0.0
        if not hasattr(self, "_source_update_rate_hz"):
            self._source_update_rate_hz = 0.0
        if not hasattr(self, "_sample_sequence"):
            self._sample_sequence = 0
