import logging
import os


LOGGER = logging.getLogger(__name__)


def _get_bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in ("1", "true", "t", "yes", "on")


def timing_debug_enabled():
    return _get_bool_env("ROBO_NECK_DEBUG_TIMING", False)


def camera_diagnostics_enabled():
    return not _get_bool_env("ROBO_NECK_DISABLE_CAMERA_DIAGNOSTICS", False)


class RuntimeTimingTracker(object):
    def __init__(
        self,
        name,
        enabled=False,
        log_every_sec=5.0,
        slow_threshold_ms=None,
        logger=None,
    ):
        self.name = str(name)
        self.enabled = bool(enabled)
        self.log_every_sec = float(log_every_sec)
        self.slow_threshold_ms = None if slow_threshold_ms is None else float(slow_threshold_ms)
        self.logger = logger or LOGGER
        self._count = 0
        self._total_ms = 0.0
        self._last_ms = 0.0
        self._max_ms = 0.0
        self._last_emit_sec = None

    def record(self, duration_ms, now=None, extra=None):
        duration_ms = float(duration_ms)
        self._count += 1
        self._total_ms += duration_ms
        self._last_ms = duration_ms
        self._max_ms = max(self._max_ms, duration_ms)

        if not self.enabled:
            return

        should_log = False
        level = logging.INFO

        if self.slow_threshold_ms is not None and duration_ms >= self.slow_threshold_ms:
            should_log = True
            level = logging.WARNING

        if self._last_emit_sec is None or (
            now is not None and (float(now) - float(self._last_emit_sec)) >= self.log_every_sec
        ):
            should_log = True

        if not should_log:
            return

        self._last_emit_sec = float(now) if now is not None else self._last_emit_sec
        snapshot = self.snapshot()
        parts = [
            "timing[{name}]".format(name=self.name),
            "last_ms={value:.1f}".format(value=snapshot["last_ms"]),
            "avg_ms={value:.1f}".format(value=snapshot["avg_ms"]),
            "max_ms={value:.1f}".format(value=snapshot["max_ms"]),
            "count={value}".format(value=snapshot["count"]),
        ]
        if extra:
            for key in sorted(extra):
                parts.append("{key}={value}".format(key=key, value=extra[key]))
        self.logger.log(level, " ".join(parts))

    def snapshot(self):
        average = self._total_ms / self._count if self._count else 0.0
        return {
            "count": int(self._count),
            "last_ms": round(self._last_ms, 3),
            "max_ms": round(self._max_ms, 3),
            "avg_ms": round(average, 3),
        }
