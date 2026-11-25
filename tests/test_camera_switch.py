import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from fastapi import HTTPException

from app.camera import CameraManager
from app.main import app, api_camera_source, video_feed


class CameraSwitchTests(unittest.TestCase):
    @patch("app.camera.WebcamReader")
    @patch("app.camera.RTSPReader")
    def test_tapo_is_startup_default_and_switches_to_webcam(
        self,
        rtsp_reader_class,
        webcam_reader_class,
    ):
        rtsp = MagicMock()
        rtsp.connected = False
        rtsp.last_error = "A aguardar..."
        rtsp_reader_class.return_value = rtsp

        webcam = MagicMock()
        webcam.connected = True
        webcam.last_error = None
        webcam_reader_class.return_value = webcam

        manager = CameraManager("rtsp://credentials@camera/stream1")
        self.assertEqual(manager.source, "tapo")
        rtsp_reader_class.assert_called_once_with(
            "rtsp://credentials@camera/stream1",
            reconnect_seconds=5,
        )

        manager.start()
        rtsp.start.assert_called_once_with()

        status = manager.switch_source("webcam")
        rtsp.stop.assert_called_once_with(timeout=5)
        webcam.start.assert_called_once_with()
        webcam_reader_class.assert_called_once_with(
            camera_index=0,
            reconnect_seconds=5,
        )
        self.assertEqual(status["source"], "webcam")
        self.assertTrue(status["connected"])

    @patch("app.camera.RTSPReader")
    def test_invalid_source_is_rejected(self, rtsp_reader_class):
        rtsp = MagicMock()
        rtsp.connected = False
        rtsp.last_error = None
        rtsp_reader_class.return_value = rtsp
        manager = CameraManager("rtsp://camera/stream1")
        with self.assertRaises(ValueError):
            manager.switch_source("usb")

    def test_api_rejects_invalid_source(self):
        app.state.runtime = SimpleNamespace(camera=MagicMock())
        with self.assertRaises(HTTPException) as context:
            api_camera_source({"source": "usb"})
        self.assertEqual(context.exception.status_code, 422)

    def test_api_switches_with_valid_source(self):
        camera = MagicMock()
        camera.switch_source.return_value = {
            "source": "webcam",
            "source_label": "Câmara do PC",
            "connected": True,
            "error": None,
        }
        app.state.runtime = SimpleNamespace(camera=camera)
        status = api_camera_source({"source": "webcam"})
        camera.switch_source.assert_called_once_with("webcam")
        self.assertEqual(status["source"], "webcam")

    def test_video_feed_streams_latest_camera_frame_directly(self):
        frame = np.zeros((24, 48, 3), dtype=np.uint8)
        runtime = SimpleNamespace(
            camera=SimpleNamespace(
                get_frame_with_sequence=MagicMock(return_value=(frame, 1))
            ),
            stop_event=threading.Event(),
        )
        with patch.object(app.state, "runtime", runtime, create=True):
            response = video_feed()

        async def read_first_frame():
            chunk = await response.body_iterator.__anext__()
            await response.body_iterator.aclose()
            return chunk

        chunk = asyncio.run(read_first_frame())
        self.assertIn(b"--frame\r\n", chunk)
        self.assertIn(b"\xff\xd8", chunk)


if __name__ == "__main__":
    unittest.main()
