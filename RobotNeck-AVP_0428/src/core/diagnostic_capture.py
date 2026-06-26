import atexit
import json
import os
import time


NEXT_STEPS_BY_CAUSE = {
    "diagnostic_timestamp_mismatch": [
        "升级到包含统一时间戳修复的版本后重新采样，避免旧版 pose_age_ms 误报。",
        "复测时优先记录 tracking_only 与 streaming 两种模式，确认真实延迟来源。",
    ],
    "avp_session_switch_latency": [
        "重点复现 session 切换前后 10-20 秒窗口，并检查是否长时间停留在 wait_ready。",
        "先做 tracking_only 基线，再切到 streaming 对比首帧等待时间。",
    ],
    "avp_input_stale": [
        "优先检查 Vision Pro pose 推流是否连续，复现时记录 stale_sample 与 sample_missing 次数。",
        "先在 tracking_only 模式复测，排除视频流并发带来的上游干扰。",
    ],
    "avp_repeated_pose": [
        "重点检查 AVP 上游是否持续返回相同 head matrix 或相同 timestamp。",
        "复测时观察 source_update_rate_hz 与 receive_rate_hz；如果 receive 正常但 source 不变，问题在上游位姿更新。",
    ],
    "avp_repeated_source_timestamp": [
        "重点检查 AVP 上游是否重复发送相同 timestamp。",
        "如果 head matrix 在变但 timestamp 不变，说明上游时间戳链路有缓存或复用问题。",
    ],
    "avp_source_flatline": [
        "查看连续 snapshot 的 sample_sequence 是否停在同一个值，同时 receive_rate_hz 仍保持较高。",
        "若 source_update_rate_hz 长时间低于 receive_rate_hz，优先排查 AVP 上游是否在重复发旧位姿。",
    ],
    "stale_command_skipped": [
        "控制层已跳过 stale 位姿对应的电机指令；先修复 AVP 位姿新鲜度，再调整电机参数。",
        "查看 skipped_stale_commands 增长区间对应的 pose_reason 和 source_update_rate_hz。",
    ],
    "camera_pipeline_contention": [
        "检查相机 frame_age_ms 与 camera_read 耗时，必要时降低分辨率或关闭额外相机处理。",
        "做一次关闭视频流或相机诊断的 A/B 对比，确认是否为相机链路拖慢。",
    ],
    "ui_control_thread_contention": [
        "先做 tracking_only 与 streaming A/B，对比 avp_read、video_callback、control_loop 三项耗时。",
        "如果 streaming 明显更重，优先缩减 UI/视频刷新负载，而不是先改电机参数。",
    ],
    "video_stream_pose_degradation": [
        "保持 1080p30 时优先降低视频码率和预览负载，观察 source_update_rate_hz 是否恢复。",
        "如果仍卡顿，再做 1080p30 与 720p30/720p60 的 A/B 对比，确认视频链路负载阈值。",
    ],
    "motor_write_bottleneck": [
        "现场检查串口稳定性和单次电机写入耗时，确认是否存在总线阻塞或重试。",
        "在上游 timing 正常时，再评估电机 profile 与写指令批量化设置。",
    ],
    "no_clear_bottleneck": [
        "延长采样时间并复现更明显的卡顿瞬间，避免样本不足掩盖真实瓶颈。",
        "分别做 tracking_only、streaming、重连后三种场景，缩小问题范围。",
    ],
    "insufficient_data": [
        "重新采样并确保问题复现持续数秒以上，再关闭 GUI 生成完整 summary。",
    ],
}


def diagnostic_capture_enabled():
    value = os.getenv("ROBO_NECK_DIAG_CAPTURE", "")
    return str(value).strip().lower() in ("1", "true", "t", "yes", "on")


class DiagnosticCaptureSession(object):
    def __init__(self, output_dir=None, enabled=False):
        self.enabled = bool(enabled)
        self.output_dir = output_dir
        self._events = []
        self._events_path = None
        self._summary_json_path = None
        self._summary_txt_path = None
        self._closed = False
        if self.enabled:
            self.output_dir = self.output_dir or self._default_output_dir()
            if not os.path.isdir(self.output_dir):
                os.makedirs(self.output_dir)
            self._events_path = os.path.join(self.output_dir, "events.jsonl")
            self._summary_json_path = os.path.join(self.output_dir, "summary.json")
            self._summary_txt_path = os.path.join(self.output_dir, "summary.txt")
            atexit.register(self.close)

    def _default_output_dir(self):
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        return os.path.join(os.getcwd(), "diagnostics", stamp)

    def record_snapshot(self, kind, payload, now=None):
        if not self.enabled or self._closed:
            return
        event = {
            "kind": str(kind),
            "ts": float(now if now is not None else time.time()),
            "payload": dict(payload or {}),
        }
        self._events.append(event)
        with open(self._events_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True))
            handle.write("\n")

    def build_summary(self):
        snapshots = [item["payload"] for item in self._events if item.get("kind") == "app_snapshot"]
        switch_events = [item["payload"] for item in self._events if item.get("kind") == "avp_switch_event"]
        summary = {
            "samples": len(snapshots),
            "top_cause": {"id": "insufficient_data", "reason": "Not enough diagnostic samples."},
            "ranked_causes": [],
        }
        if not snapshots and not switch_events:
            return summary

        idle_reasons = {"idle", "disconnected"}
        tracking_samples = [item for item in snapshots if bool(item.get("tracking", False))]
        idle_samples = [
            item for item in snapshots
            if not bool(item.get("tracking", False)) and str(item.get("pose_reason") or "") in idle_reasons
        ]
        tracking_only_samples = [
            item for item in tracking_samples if str(item.get("session_mode") or "tracking_only") == "tracking_only"
        ]
        streaming_tracking_samples = [
            item for item in tracking_samples if str(item.get("session_mode") or "") == "streaming"
        ]

        def avg_number(items, getter):
            values = []
            for item in items:
                value = getter(item)
                if isinstance(value, (int, float)):
                    values.append(float(value))
            if not values:
                return 0.0
            return round(sum(values) / len(values), 3)

        tracking_only_avg_receive_rate = avg_number(tracking_only_samples, lambda item: item.get("avp_receive_rate_hz"))
        tracking_only_avg_source_rate = avg_number(tracking_only_samples, lambda item: item.get("avp_source_update_rate_hz"))
        tracking_only_avg_pose_age = avg_number(tracking_only_samples, lambda item: item.get("pose_age_ms"))
        tracking_only_avg_motor_gap = avg_number(tracking_only_samples, lambda item: item.get("motor_command_gap_ms"))
        tracking_only_avg_repeated_pose = avg_number(tracking_only_samples, lambda item: item.get("avp_repeated_head_matrix_count"))
        streaming_avg_receive_rate = avg_number(streaming_tracking_samples, lambda item: item.get("avp_receive_rate_hz"))
        streaming_avg_source_rate = avg_number(streaming_tracking_samples, lambda item: item.get("avp_source_update_rate_hz"))
        streaming_avg_pose_age = avg_number(streaming_tracking_samples, lambda item: item.get("pose_age_ms"))
        streaming_avg_motor_gap = avg_number(streaming_tracking_samples, lambda item: item.get("motor_command_gap_ms"))
        streaming_avg_repeated_pose = avg_number(streaming_tracking_samples, lambda item: item.get("avp_repeated_head_matrix_count"))
        streaming_video_callback_avg_ms = avg_number(
            streaming_tracking_samples,
            lambda item: ((item.get("timing") or {}).get("video_callback") or {}).get("avg_ms"),
        )
        streaming_video_callback_max_ms = avg_number(
            streaming_tracking_samples,
            lambda item: ((item.get("timing") or {}).get("video_callback") or {}).get("max_ms"),
        )

        timestamp_mismatch = sum(
            1 for item in tracking_samples
            if bool(item.get("pose_fresh", False)) and float(item.get("pose_age_ms") or 0.0) > 10000.0
        )

        stale_count = sum(1 for item in tracking_samples if not bool(item.get("pose_fresh", False)))
        high_pose_age = sum(
            1 for item in tracking_samples
            if not bool(item.get("pose_fresh", False)) and float(item.get("pose_age_ms") or 0.0) > 250.0
        )
        slow_loop = sum(
            1 for item in tracking_samples
            if float(item.get("loop_rate_hz") or 0.0) > 0.0 and float(item.get("loop_rate_hz") or 0.0) < 40.0
        )
        camera_old = sum(1 for item in snapshots if float((item.get("camera") or {}).get("frame_age_ms") or 0.0) > 150.0)
        camera_fail = sum(1 for item in snapshots if int((item.get("camera") or {}).get("read_failures") or 0) > 0)
        update_slow = sum(
            1 for item in tracking_samples
            if float(((item.get("timing") or {}).get("update_loop") or {}).get("avg_ms") or 0.0) > 25.0
        )
        control_slow = sum(
            1 for item in tracking_samples
            if float(((item.get("timing") or {}).get("control_loop") or {}).get("avg_ms") or 0.0) > 20.0
        )
        camera_read_slow = sum(
            1 for item in snapshots if float(((item.get("timing") or {}).get("camera_read") or {}).get("avg_ms") or 0.0) > 20.0
        )
        motor_slow = sum(
            1 for item in tracking_samples
            if float(((item.get("timing") or {}).get("motor_write") or {}).get("avg_ms") or 0.0) > 8.0
        )
        repeated_pose = sum(
            1 for item in tracking_samples
            if int(item.get("avp_repeated_head_matrix_count") or 0) >= 5
        )
        repeated_source_timestamp = sum(
            1 for item in tracking_samples
            if int(item.get("avp_repeated_source_timestamp_count") or 0) >= 5
        )
        source_flatline_samples = 0
        source_flatline_max_run = 0
        source_flatline_run = 0
        previous_sequence = None
        for item in tracking_samples:
            sequence = item.get("avp_sample_sequence")
            receive_rate = float(item.get("avp_receive_rate_hz") or 0.0)
            if (
                isinstance(sequence, int)
                and previous_sequence is not None
                and sequence == previous_sequence
                and receive_rate >= 50.0
            ):
                source_flatline_samples += 1
                source_flatline_run += 1
                source_flatline_max_run = max(source_flatline_max_run, source_flatline_run)
            else:
                source_flatline_run = 0
            previous_sequence = sequence if isinstance(sequence, int) else previous_sequence
        skipped_stale_commands = sum(int(item.get("skipped_stale_commands") or 0) for item in tracking_samples)
        unchanged_target_skips = sum(int(item.get("unchanged_target_skips") or 0) for item in tracking_samples)
        motor_write_errors = sum(int(item.get("motor_write_errors") or 0) for item in tracking_samples)
        switch_wait_events = [
            item for item in switch_events
            if item.get("name") == "avp_switch_wait_ready_done" and float(item.get("duration_ms") or 0.0) > 1200.0
        ]
        switch_total_events = [
            item for item in switch_events
            if item.get("name") == "avp_switch_complete" and float(item.get("total_ms") or 0.0) > 1500.0
        ]

        ranked = []
        waiting_first_sample = sum(
            1 for item in tracking_samples if str(item.get("pose_reason") or "") == "stream_established_waiting_first_sample"
        )
        if timestamp_mismatch:
            ranked.append(
                {
                    "id": "diagnostic_timestamp_mismatch",
                    "score": timestamp_mismatch * 5,
                    "reason": "Pose freshness and pose age use inconsistent timestamp bases, so AVP stale metrics are unreliable.",
                }
            )
        if switch_wait_events or switch_total_events:
            ranked.append(
                {
                    "id": "avp_session_switch_latency",
                    "score": len(switch_wait_events) * 8 + len(switch_total_events) * 6 + waiting_first_sample * 2,
                    "reason": "AVP session switch spends too long waiting for the rebuilt session to become ready.",
                }
            )
        if stale_count or high_pose_age:
            ranked.append(
                {
                    "id": "avp_input_stale",
                    "score": stale_count * 3 + high_pose_age,
                    "reason": "AVP pose samples are stale or missing for a significant share of samples.",
                }
            )
        if repeated_pose:
            ranked.append(
                {
                    "id": "avp_repeated_pose",
                    "score": repeated_pose * 4 + skipped_stale_commands,
                    "reason": "AVP receive calls continue, but head pose appears repeated or not updated.",
                }
            )
        if (
            tracking_only_samples
            and streaming_tracking_samples
            and tracking_only_avg_source_rate > 0.0
            and streaming_avg_source_rate <= tracking_only_avg_source_rate * 0.65
            and streaming_video_callback_avg_ms > 0.0
        ):
            source_drop_hz = max(0.0, tracking_only_avg_source_rate - streaming_avg_source_rate)
            ranked.append(
                {
                    "id": "video_stream_pose_degradation",
                    "score": int(source_drop_hz * 4) + repeated_pose * 4,
                    "reason": "Opening video streaming correlates with lower AVP source update rate and more repeated pose samples.",
                }
            )
        if repeated_source_timestamp:
            ranked.append(
                {
                    "id": "avp_repeated_source_timestamp",
                    "score": repeated_source_timestamp * 4,
                    "reason": "AVP receive calls continue, but source timestamp appears repeated across samples.",
                }
            )
        if source_flatline_samples:
            ranked.append(
                {
                    "id": "avp_source_flatline",
                    "score": source_flatline_samples * 3 + source_flatline_max_run * 6,
                    "reason": "AVP receive calls continue, but sample_sequence stops advancing across consecutive snapshots.",
                }
            )
        if skipped_stale_commands and not repeated_pose:
            ranked.append(
                {
                    "id": "stale_command_skipped",
                    "score": skipped_stale_commands,
                    "reason": "Motor commands were intentionally skipped because pose samples were stale.",
                }
            )
        if camera_old or camera_fail or camera_read_slow:
            ranked.append(
                {
                    "id": "camera_pipeline_contention",
                    "score": camera_old * 2 + camera_fail * 2 + camera_read_slow,
                    "reason": "Camera frame age or camera read latency indicates capture contention or blocking.",
                }
            )
        if update_slow or control_slow or slow_loop:
            ranked.append(
                {
                    "id": "ui_control_thread_contention",
                    "score": update_slow * 2 + control_slow * 2 + slow_loop,
                    "reason": "UI/update or control-loop timing suggests the main loop is overloaded.",
                }
            )
        if motor_slow or motor_write_errors:
            ranked.append(
                {
                    "id": "motor_write_bottleneck",
                    "score": motor_slow + motor_write_errors * 4,
                    "reason": "Motor write timing is elevated while upstream timings are comparatively lower.",
                }
            )

        if not ranked:
            ranked.append(
                {
                    "id": "no_clear_bottleneck",
                    "score": 1,
                    "reason": "No dominant bottleneck was detected in the captured samples.",
                }
            )

        ranked.sort(key=lambda item: item["score"], reverse=True)
        summary["top_cause"] = {"id": ranked[0]["id"], "reason": ranked[0]["reason"]}
        summary["ranked_causes"] = ranked
        summary["next_steps"] = list(NEXT_STEPS_BY_CAUSE.get(ranked[0]["id"], NEXT_STEPS_BY_CAUSE["no_clear_bottleneck"]))
        summary["stats"] = {
            "stale_count": stale_count,
            "high_pose_age": high_pose_age,
            "slow_loop": slow_loop,
            "camera_old": camera_old,
            "camera_fail": camera_fail,
            "update_slow": update_slow,
            "control_slow": control_slow,
            "camera_read_slow": camera_read_slow,
            "motor_slow": motor_slow,
            "repeated_pose": repeated_pose,
            "repeated_source_timestamp": repeated_source_timestamp,
            "source_flatline_samples": source_flatline_samples,
            "source_flatline_max_run": source_flatline_max_run,
            "skipped_stale_commands": skipped_stale_commands,
            "unchanged_target_skips": unchanged_target_skips,
            "motor_write_errors": motor_write_errors,
            "switch_wait_events": len(switch_wait_events),
            "switch_total_events": len(switch_total_events),
            "waiting_first_sample": waiting_first_sample,
            "tracking_samples": len(tracking_samples),
            "idle_samples": len(idle_samples),
            "tracking_only_samples": len(tracking_only_samples),
            "streaming_tracking_samples": len(streaming_tracking_samples),
            "timestamp_mismatch": timestamp_mismatch,
            "tracking_only_avg_receive_rate_hz": tracking_only_avg_receive_rate,
            "tracking_only_avg_source_update_rate_hz": tracking_only_avg_source_rate,
            "tracking_only_avg_pose_age_ms": tracking_only_avg_pose_age,
            "tracking_only_avg_motor_command_gap_ms": tracking_only_avg_motor_gap,
            "tracking_only_avg_repeated_head_matrix_count": tracking_only_avg_repeated_pose,
            "streaming_avg_receive_rate_hz": streaming_avg_receive_rate,
            "streaming_avg_source_update_rate_hz": streaming_avg_source_rate,
            "streaming_avg_pose_age_ms": streaming_avg_pose_age,
            "streaming_avg_motor_command_gap_ms": streaming_avg_motor_gap,
            "streaming_avg_repeated_head_matrix_count": streaming_avg_repeated_pose,
            "streaming_video_callback_avg_ms": streaming_video_callback_avg_ms,
            "streaming_video_callback_max_ms": streaming_video_callback_max_ms,
        }
        return summary

    def close(self):
        if not self.enabled or self._closed:
            return
        summary = self.build_summary()
        with open(self._summary_json_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
        with open(self._summary_txt_path, "w", encoding="utf-8") as handle:
            handle.write("Diagnostic Summary\n")
            handle.write("==================\n")
            handle.write("Top cause: {0}\n".format(summary["top_cause"]["id"]))
            handle.write("{0}\n\n".format(summary["top_cause"]["reason"]))
            for item in summary.get("ranked_causes", []):
                handle.write("- {id}: {reason}\n".format(**item))
            stats = summary.get("stats") or {}
            if any(
                int(stats.get(key) or 0) > 0
                for key in (
                    "repeated_pose",
                    "repeated_source_timestamp",
                    "source_flatline_samples",
                    "unchanged_target_skips",
                    "skipped_stale_commands",
                )
            ):
                handle.write("\nAVP repetition signals:\n")
                handle.write("- repeated_head_matrix_snapshots: {0}\n".format(int(stats.get("repeated_pose") or 0)))
                handle.write("- repeated_source_timestamp_snapshots: {0}\n".format(int(stats.get("repeated_source_timestamp") or 0)))
                handle.write("- source_flatline_samples: {0}\n".format(int(stats.get("source_flatline_samples") or 0)))
                handle.write("- source_flatline_max_run: {0}\n".format(int(stats.get("source_flatline_max_run") or 0)))
                handle.write("- unchanged_target_skips: {0}\n".format(int(stats.get("unchanged_target_skips") or 0)))
                handle.write("- skipped_stale_commands: {0}\n".format(int(stats.get("skipped_stale_commands") or 0)))
            if int(stats.get("tracking_only_samples") or 0) and int(stats.get("streaming_tracking_samples") or 0):
                handle.write("\nTracking vs streaming:\n")
                handle.write("- tracking_only_source_update_rate_hz: {0}\n".format(stats.get("tracking_only_avg_source_update_rate_hz") or 0.0))
                handle.write("- streaming_source_update_rate_hz: {0}\n".format(stats.get("streaming_avg_source_update_rate_hz") or 0.0))
                handle.write("- tracking_only_receive_rate_hz: {0}\n".format(stats.get("tracking_only_avg_receive_rate_hz") or 0.0))
                handle.write("- streaming_receive_rate_hz: {0}\n".format(stats.get("streaming_avg_receive_rate_hz") or 0.0))
                handle.write("- tracking_only_pose_age_ms: {0}\n".format(stats.get("tracking_only_avg_pose_age_ms") or 0.0))
                handle.write("- streaming_pose_age_ms: {0}\n".format(stats.get("streaming_avg_pose_age_ms") or 0.0))
                handle.write("- tracking_only_motor_command_gap_ms: {0}\n".format(stats.get("tracking_only_avg_motor_command_gap_ms") or 0.0))
                handle.write("- streaming_motor_command_gap_ms: {0}\n".format(stats.get("streaming_avg_motor_command_gap_ms") or 0.0))
                handle.write("- tracking_only_repeated_head_matrix_count: {0}\n".format(stats.get("tracking_only_avg_repeated_head_matrix_count") or 0.0))
                handle.write("- streaming_repeated_head_matrix_count: {0}\n".format(stats.get("streaming_avg_repeated_head_matrix_count") or 0.0))
                handle.write("- streaming_video_callback_avg_ms: {0}\n".format(stats.get("streaming_video_callback_avg_ms") or 0.0))
                handle.write("- streaming_video_callback_max_ms: {0}\n".format(stats.get("streaming_video_callback_max_ms") or 0.0))
            if summary.get("next_steps"):
                handle.write("\nNext steps:\n")
                for item in summary["next_steps"]:
                    handle.write("- {0}\n".format(item))
        self._closed = True
