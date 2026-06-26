import json
import os
import sys


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.core.diagnostic_capture import DiagnosticCaptureSession


def test_diagnostic_capture_marks_avp_staleness_as_top_cause(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    for index in range(5):
        session.record_snapshot(
            "app_snapshot",
            {
                "tracking": True,
                "session_mode": "tracking_only",
                "pose_reason": "stale_sample",
                "pose_fresh": False,
                "pose_age_ms": 1200.0 + index,
                "loop_rate_hz": 58.0,
                "motor_command_gap_ms": 40.0,
                "camera": {"frame_age_ms": 30.0, "read_failures": 0},
                "timing": {
                    "avp_read": {"avg_ms": 4.0, "max_ms": 7.0},
                    "camera_read": {"avg_ms": 6.0, "max_ms": 9.0},
                    "update_loop": {"avg_ms": 8.0, "max_ms": 12.0},
                    "control_loop": {"avg_ms": 7.0, "max_ms": 11.0},
                    "motor_write": {"avg_ms": 2.0, "max_ms": 3.0},
                },
            },
        )

    summary = session.build_summary()

    assert summary["top_cause"]["id"] == "avp_input_stale"
    assert "stale" in summary["top_cause"]["reason"]


def test_diagnostic_capture_writes_summary_files(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    session.record_snapshot(
        "app_snapshot",
        {
            "pose_reason": "ready",
            "pose_fresh": True,
            "pose_age_ms": 18.0,
            "loop_rate_hz": 18.0,
            "motor_command_gap_ms": 80.0,
            "camera": {"frame_age_ms": 250.0, "read_failures": 4},
            "timing": {
                "avp_read": {"avg_ms": 3.0, "max_ms": 5.0},
                "camera_read": {"avg_ms": 45.0, "max_ms": 90.0},
                "update_loop": {"avg_ms": 35.0, "max_ms": 60.0},
                "control_loop": {"avg_ms": 30.0, "max_ms": 50.0},
                "motor_write": {"avg_ms": 2.0, "max_ms": 3.0},
            },
        },
    )

    session.close()

    summary_json = tmp_path / "summary.json"
    summary_txt = tmp_path / "summary.txt"
    events_jsonl = tmp_path / "events.jsonl"

    assert summary_json.exists()
    assert summary_txt.exists()
    assert events_jsonl.exists()

    payload = json.loads(summary_json.read_text())
    assert payload["top_cause"]["id"] == "camera_pipeline_contention"
    assert "camera" in summary_txt.read_text().lower()


def test_diagnostic_capture_identifies_session_switch_wait_bottleneck(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    for _ in range(3):
        session.record_snapshot(
            "app_snapshot",
            {
                "pose_reason": "stream_established_waiting_first_sample",
                "pose_fresh": False,
                "pose_age_ms": None,
                "loop_rate_hz": 55.0,
                "motor_command_gap_ms": None,
                "camera": {"frame_age_ms": 20.0, "read_failures": 0},
                "timing": {
                    "avp_read": {"avg_ms": 3.0, "max_ms": 4.0},
                    "camera_read": {"avg_ms": 5.0, "max_ms": 7.0},
                    "update_loop": {"avg_ms": 9.0, "max_ms": 11.0},
                    "control_loop": {"avg_ms": 7.0, "max_ms": 9.0},
                    "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
                },
            },
        )
    session.record_snapshot(
        "avp_switch_event",
        {
            "name": "avp_switch_wait_ready_done",
            "target_mode": "streaming",
            "duration_ms": 1650.0,
            "success": True,
        },
    )

    summary = session.build_summary()

    assert summary["top_cause"]["id"] == "avp_session_switch_latency"
    assert "switch" in summary["top_cause"]["reason"]


def test_diagnostic_capture_ignores_idle_samples_when_scoring_stale_and_slow_loop(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    for _ in range(4):
        session.record_snapshot(
            "app_snapshot",
            {
                "tracking": False,
                "pose_reason": "idle",
                "pose_fresh": False,
                "pose_age_ms": None,
                "loop_rate_hz": 0.0,
                "camera": {"frame_age_ms": 20.0, "read_failures": 0},
                "timing": {
                    "avp_read": {"avg_ms": 0.0, "max_ms": 0.0},
                    "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                    "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                    "control_loop": {"avg_ms": 0.0, "max_ms": 0.0},
                    "motor_write": {"avg_ms": 0.0, "max_ms": 0.0},
                },
            },
        )
    session.record_snapshot(
        "app_snapshot",
        {
            "tracking": True,
            "session_mode": "tracking_only",
            "pose_reason": "ready",
            "pose_fresh": True,
            "pose_age_ms": 18.0,
            "loop_rate_hz": 58.0,
            "camera": {"frame_age_ms": 20.0, "read_failures": 0},
            "timing": {
                "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
            },
        },
    )

    summary = session.build_summary()

    assert summary["top_cause"]["id"] == "no_clear_bottleneck"
    assert summary["stats"]["idle_samples"] == 4
    assert summary["stats"]["tracking_samples"] == 1
    assert summary["stats"]["stale_count"] == 0
    assert summary["stats"]["slow_loop"] == 0


def test_diagnostic_capture_flags_timestamp_mismatch_before_avp_stale(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    for _ in range(3):
        session.record_snapshot(
            "app_snapshot",
            {
                "tracking": True,
                "session_mode": "tracking_only",
                "pose_reason": "ready",
                "pose_fresh": True,
                "pose_age_ms": 1_777_034_701_040.7,
                "loop_rate_hz": 58.0,
                "camera": {"frame_age_ms": 25.0, "read_failures": 0},
                "timing": {
                    "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                    "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                    "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                    "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                    "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
                },
            },
        )

    summary = session.build_summary()

    assert summary["top_cause"]["id"] == "diagnostic_timestamp_mismatch"
    assert summary["stats"]["timestamp_mismatch"] == 3
    assert summary["next_steps"]
    assert any("重新采样" in item for item in summary["next_steps"])


def test_diagnostic_capture_identifies_repeated_pose_and_skipped_stale_commands(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    for _ in range(4):
        session.record_snapshot(
            "app_snapshot",
            {
                "tracking": True,
                "session_mode": "tracking_only",
                "pose_reason": "stale_sample",
                "pose_fresh": False,
                "pose_age_ms": 650.0,
                "loop_rate_hz": 58.0,
                "motor_command_gap_ms": 80.0,
                "avp_repeated_head_matrix_count": 12,
                "skipped_stale_commands": 3,
                "unchanged_target_skips": 0,
                "motor_write_errors": 0,
                "camera": {"frame_age_ms": 25.0, "read_failures": 0},
                "timing": {
                    "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                    "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                    "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                    "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                    "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
                },
            },
        )

    summary = session.build_summary()

    assert summary["top_cause"]["id"] == "avp_repeated_pose"
    assert summary["stats"]["repeated_pose"] == 4
    assert summary["stats"]["skipped_stale_commands"] == 12


def test_diagnostic_capture_identifies_source_flatline_when_receive_continues(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    snapshots = [
        {
            "tracking": True,
            "session_mode": "streaming",
            "pose_reason": "ready",
            "pose_fresh": True,
            "pose_age_ms": 24.0,
            "loop_rate_hz": 104.0,
            "avp_receive_rate_hz": 112.0,
            "avp_source_update_rate_hz": 4.0,
            "avp_sample_sequence": 258,
            "avp_repeated_head_matrix_count": 0,
            "unchanged_target_skips": 18,
            "skipped_stale_commands": 0,
            "motor_write_errors": 0,
            "camera": {"frame_age_ms": 20.0, "read_failures": 0},
            "timing": {
                "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
            },
        },
        {
            "tracking": True,
            "session_mode": "streaming",
            "pose_reason": "ready",
            "pose_fresh": True,
            "pose_age_ms": 25.0,
            "loop_rate_hz": 105.0,
            "avp_receive_rate_hz": 110.0,
            "avp_source_update_rate_hz": 4.0,
            "avp_sample_sequence": 258,
            "avp_repeated_head_matrix_count": 0,
            "unchanged_target_skips": 21,
            "skipped_stale_commands": 0,
            "motor_write_errors": 0,
            "camera": {"frame_age_ms": 21.0, "read_failures": 0},
            "timing": {
                "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
            },
        },
        {
            "tracking": True,
            "session_mode": "streaming",
            "pose_reason": "ready",
            "pose_fresh": True,
            "pose_age_ms": 26.0,
            "loop_rate_hz": 103.0,
            "avp_receive_rate_hz": 111.0,
            "avp_source_update_rate_hz": 4.0,
            "avp_sample_sequence": 258,
            "avp_repeated_head_matrix_count": 0,
            "unchanged_target_skips": 24,
            "skipped_stale_commands": 0,
            "motor_write_errors": 0,
            "camera": {"frame_age_ms": 22.0, "read_failures": 0},
            "timing": {
                "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
            },
        },
        {
            "tracking": True,
            "session_mode": "streaming",
            "pose_reason": "ready",
            "pose_fresh": True,
            "pose_age_ms": 27.0,
            "loop_rate_hz": 102.0,
            "avp_receive_rate_hz": 109.0,
            "avp_source_update_rate_hz": 4.0,
            "avp_sample_sequence": 258,
            "avp_repeated_head_matrix_count": 0,
            "unchanged_target_skips": 27,
            "skipped_stale_commands": 0,
            "motor_write_errors": 0,
            "camera": {"frame_age_ms": 22.0, "read_failures": 0},
            "timing": {
                "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
            },
        },
    ]

    for snapshot in snapshots:
        session.record_snapshot("app_snapshot", snapshot)

    summary = session.build_summary()

    assert any(item["id"] == "avp_source_flatline" for item in summary["ranked_causes"])
    assert summary["stats"]["source_flatline_samples"] == 3
    assert summary["stats"]["source_flatline_max_run"] == 3


def test_diagnostic_summary_text_includes_avp_repetition_signal_breakdown(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    session.record_snapshot(
        "app_snapshot",
        {
            "tracking": True,
            "session_mode": "streaming",
            "pose_reason": "ready",
            "pose_fresh": True,
            "pose_age_ms": 80.0,
            "loop_rate_hz": 105.0,
            "avp_receive_rate_hz": 110.0,
            "avp_source_update_rate_hz": 8.0,
            "avp_sample_sequence": 10,
            "avp_repeated_head_matrix_count": 8,
            "avp_repeated_source_timestamp_count": 6,
            "unchanged_target_skips": 4,
            "skipped_stale_commands": 0,
            "motor_write_errors": 0,
            "camera": {"frame_age_ms": 22.0, "read_failures": 0},
            "timing": {
                "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
            },
        },
    )
    session.record_snapshot(
        "app_snapshot",
        {
            "tracking": True,
            "session_mode": "streaming",
            "pose_reason": "ready",
            "pose_fresh": True,
            "pose_age_ms": 82.0,
            "loop_rate_hz": 105.0,
            "avp_receive_rate_hz": 111.0,
            "avp_source_update_rate_hz": 8.0,
            "avp_sample_sequence": 10,
            "avp_repeated_head_matrix_count": 9,
            "avp_repeated_source_timestamp_count": 7,
            "unchanged_target_skips": 8,
            "skipped_stale_commands": 0,
            "motor_write_errors": 0,
            "camera": {"frame_age_ms": 22.0, "read_failures": 0},
            "timing": {
                "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
            },
        },
    )

    session.close()

    text = (tmp_path / "summary.txt").read_text()

    assert "AVP repetition signals:" in text
    assert "repeated_head_matrix_snapshots: 2" in text
    assert "repeated_source_timestamp_snapshots: 2" in text
    assert "source_flatline_samples: 1" in text


def test_diagnostic_capture_identifies_streaming_pose_degradation(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    base = {
        "tracking": True,
        "pose_reason": "ready",
        "pose_fresh": True,
        "loop_rate_hz": 105.0,
        "avp_receive_rate_hz": 110.0,
        "avp_repeated_head_matrix_count": 0,
        "avp_repeated_source_timestamp_count": 0,
        "skipped_stale_commands": 0,
        "unchanged_target_skips": 0,
        "motor_write_errors": 0,
        "camera": {"frame_age_ms": 25.0, "read_failures": 0},
        "timing": {
            "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
            "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
            "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
            "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
            "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
            "video_callback": {"avg_ms": 0.0, "max_ms": 0.0},
        },
    }
    for _ in range(4):
        snapshot = dict(base, session_mode="tracking_only", avp_source_update_rate_hz=60.0, pose_age_ms=8.0, motor_command_gap_ms=20.0)
        session.record_snapshot("app_snapshot", snapshot)
    for _ in range(4):
        snapshot = dict(
            base,
            session_mode="streaming",
            streaming=True,
            avp_source_update_rate_hz=15.0,
            pose_age_ms=65.0,
            motor_command_gap_ms=90.0,
            avp_repeated_head_matrix_count=8,
            unchanged_target_skips=120,
            timing={**base["timing"], "video_callback": {"avg_ms": 3.5, "max_ms": 14.0}},
        )
        session.record_snapshot("app_snapshot", snapshot)

    summary = session.build_summary()

    assert summary["top_cause"]["id"] == "video_stream_pose_degradation"
    assert summary["stats"]["tracking_only_avg_source_update_rate_hz"] == 60.0
    assert summary["stats"]["streaming_avg_source_update_rate_hz"] == 15.0


def test_diagnostic_summary_text_includes_tracking_vs_streaming_comparison(tmp_path):
    session = DiagnosticCaptureSession(output_dir=str(tmp_path), enabled=True)
    for mode, source_rate, video_avg in [
        ("tracking_only", 60.0, 0.0),
        ("streaming", 20.0, 3.2),
    ]:
        session.record_snapshot(
            "app_snapshot",
            {
                "tracking": True,
                "session_mode": mode,
                "pose_reason": "ready",
                "pose_fresh": True,
                "pose_age_ms": 20.0,
                "loop_rate_hz": 100.0,
                "motor_command_gap_ms": 40.0,
                "avp_receive_rate_hz": 110.0,
                "avp_source_update_rate_hz": source_rate,
                "avp_repeated_head_matrix_count": 0,
                "camera": {"frame_age_ms": 25.0, "read_failures": 0},
                "timing": {
                    "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                    "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                    "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                    "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                    "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
                    "video_callback": {"avg_ms": video_avg, "max_ms": video_avg},
                },
            },
        )

    session.close()

    text = (tmp_path / "summary.txt").read_text()

    assert "Tracking vs streaming:" in text
    assert "tracking_only_source_update_rate_hz: 60.0" in text
    assert "streaming_source_update_rate_hz: 20.0" in text
    assert "streaming_video_callback_avg_ms: 3.2" in text
