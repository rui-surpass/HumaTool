import argparse
import json
import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

from src.core.diagnostic_capture import DiagnosticCaptureSession


def _load_events(events_path):
    events = []
    with open(events_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def _latest_diagnostics_dir(base_dir):
    if not os.path.isdir(base_dir):
        return None
    candidates = [
        os.path.join(base_dir, name)
        for name in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, name))
    ]
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1]


def _timing_stats(samples, key):
    values = []
    for item in samples:
        timing = (item.get("timing") or {}).get(key) or {}
        value = timing.get("avg_ms")
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    return {
        "avg_ms": round(sum(values) / len(values), 3),
        "max_ms": round(max(values), 3),
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize RobotNeck latency diagnostic captures.")
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Diagnostic capture directory. Defaults to the latest folder under ./diagnostics.",
    )
    args = parser.parse_args()

    input_dir = args.input_dir or _latest_diagnostics_dir(os.path.join(ROOT_DIR, "diagnostics"))
    if not input_dir:
        print("No diagnostic directory found.")
        return 1

    events_path = os.path.join(input_dir, "events.jsonl")
    if not os.path.exists(events_path):
        print("Missing events.jsonl in {0}".format(input_dir))
        return 1

    session = DiagnosticCaptureSession(output_dir=input_dir, enabled=True)
    session._events = _load_events(events_path)
    summary = session.build_summary()
    snapshots = [item["payload"] for item in session._events if item.get("kind") == "app_snapshot"]
    tracking_samples = [item for item in snapshots if bool(item.get("tracking", False))]
    tracking_only_samples = [item for item in tracking_samples if str(item.get("session_mode") or "tracking_only") == "tracking_only"]
    streaming_tracking_samples = [item for item in tracking_samples if str(item.get("session_mode") or "") == "streaming"]

    print("Diagnostic directory: {0}".format(input_dir))
    print("Samples: {0}".format(summary.get("samples", 0)))
    stats = summary.get("stats", {})
    if stats:
        print(
            "Tracking samples: {0} | Idle samples: {1}".format(
                stats.get("tracking_samples", 0),
                stats.get("idle_samples", 0),
            )
        )
        print(
            "Tracking-only samples: {0} | Streaming+tracking samples: {1}".format(
                stats.get("tracking_only_samples", 0),
                stats.get("streaming_tracking_samples", 0),
            )
        )
    print("Top cause: {0}".format(summary["top_cause"]["id"]))
    print(summary["top_cause"]["reason"])
    if stats.get("timestamp_mismatch", 0):
        print("Warning: diagnostic timestamp mismatch detected; pose-age-derived stale metrics were unreliable.")
    next_steps = summary.get("next_steps") or []
    if next_steps:
        print("")
        print("Next actions:")
        for item in next_steps:
            print("- {0}".format(item))
    print("")
    print("Ranked causes:")
    for item in summary.get("ranked_causes", []):
        print("- {id}: {reason}".format(**item))
    print("")
    print("Timing by mode:")
    for label, samples in (
        ("tracking_only", tracking_only_samples),
        ("streaming_tracking", streaming_tracking_samples),
    ):
        avp_read = _timing_stats(samples, "avp_read")
        video_callback = _timing_stats(samples, "video_callback")
        control_loop = _timing_stats(samples, "control_loop")
        if not any((avp_read, video_callback, control_loop)):
            continue
        print(
            "- {0}: avp_read={1} video_callback={2} control_loop={3}".format(
                label,
                avp_read or {},
                video_callback or {},
                control_loop or {},
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
