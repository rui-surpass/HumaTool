import os
import sys
import types


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

sys.modules.setdefault("cv2", types.SimpleNamespace())

from src.core.client import AVPClient


class FakeFrameSource:
    def __init__(self):
        self.read_calls = 0

    def read(self):
        self.read_calls += 1
        return True, f"frame-{self.read_calls}"


class FakeStreamer:
    def __init__(self):
        self.configured = []
        self.callbacks = []
        self.started_ports = []
        self.cleaned = 0

    def configure_video(self, **kwargs):
        self.configured.append(kwargs)

    def register_frame_callback(self, cb):
        self.callbacks.append(cb)

    def start_webrtc(self, port):
        self.started_ports.append(port)

    def cleanup(self):
        self.cleaned += 1


def make_client(streamer=None):
    client = AVPClient.__new__(AVPClient)
    client.streamer = streamer or FakeStreamer()
    client.running = False
    client.using_dummy_video = False
    client.frame_source = None
    return client


def test_start_video_stream_uses_external_frame_source():
    streamer = FakeStreamer()
    frame_source = FakeFrameSource()
    client = make_client(streamer=streamer)

    client.start_video_stream(
        frame_source=frame_source,
        resolution="3840x1080",
        fps=30,
        bitrate=12000,
        stereo=True,
        latency="Balanced",
    )

    assert client.frame_source is frame_source
    assert streamer.configured[-1]["size"] == "3840x1080"
    assert streamer.configured[-1]["fps"] == 30
    assert streamer.configured[-1]["bitrate"] == 12000
    assert streamer.started_ports == [9999]


def test_video_callback_reads_from_external_frame_source():
    client = make_client()
    frame_source = FakeFrameSource()
    client.frame_source = frame_source

    assert client._video_callback("blank") == "frame-1"
    assert frame_source.read_calls == 1


def test_stop_video_stream_cleans_streamer_without_camera_side_effects():
    streamer = FakeStreamer()
    client = make_client(streamer=streamer)
    client.frame_source = FakeFrameSource()
    client.session_mode = "streaming"

    client.stop_video_stream()

    assert streamer.cleaned == 1
    assert client.frame_source is None
    assert client.streamer is None
    assert client.session_mode == "tracking_only"
