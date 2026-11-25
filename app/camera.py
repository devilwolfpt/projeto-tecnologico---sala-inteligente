"""Leitura das fontes de vídeo numa thread dedicada."""

import logging
import sys
import threading
from typing import Optional

import cv2
import numpy as np


logger = logging.getLogger(__name__)


class RTSPReader:
    """Mantém apenas o frame mais recente e reconecta quando o stream falha."""

    def __init__(self, rtsp_url: str, reconnect_seconds: int = 5) -> None:
        if reconnect_seconds < 1:
            raise ValueError("reconnect_seconds tem de ser pelo menos 1.")
        self._rtsp_url = rtsp_url
        self._reconnect_seconds = reconnect_seconds
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_sequence = 0
        self._connected = False
        self._last_error: Optional[str] = None

    @property
    def connected(self) -> bool:
        """Indica se a última leitura da câmara teve sucesso."""
        with self._lock:
            return self._connected

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def start(self) -> "RTSPReader":
        """Inicia a thread de leitura, se ainda não estiver em execução."""
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop,
            name="rtsp-reader",
            daemon=True,
        )
        self._thread.start()
        return self

    def get_frame(self) -> Optional[np.ndarray]:
        """Devolve uma cópia do frame mais recente, ou None se ainda não existir."""
        frame, _ = self.get_frame_with_sequence()
        return frame

    def get_frame_with_sequence(
        self,
    ) -> tuple[Optional[np.ndarray], Optional[int]]:
        """Devolve o frame e o número de sequência da última leitura."""
        with self._lock:
            if self._latest_frame is None:
                return None, None
            return self._latest_frame.copy(), self._frame_sequence

    def stop(self, timeout: float = 10.0) -> None:
        """Pede à thread que termine e aguarda a sua saída."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "A thread RTSP não terminou dentro de %.1f segundos.", timeout
                )

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            capture: Optional[cv2.VideoCapture] = None
            try:
                capture = cv2.VideoCapture(self._rtsp_url, cv2.CAP_FFMPEG)
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not capture.isOpened():
                    with self._lock:
                        self._last_error = (
                            "Não foi possível ligar à Câmara Tapo. "
                            "A tentar novamente..."
                        )
                    logger.warning(
                        "Não foi possível abrir o stream RTSP; nova tentativa em %s s.",
                        self._reconnect_seconds,
                    )
                else:
                    with self._lock:
                        self._connected = True
                        self._last_error = None
                    logger.info("Ligação ao stream RTSP estabelecida.")

                    while not self._stop_event.is_set():
                        success, frame = capture.read()
                        if not success or frame is None:
                            with self._lock:
                                self._last_error = (
                                    "A leitura da Câmara Tapo falhou. "
                                    "A tentar novamente..."
                                )
                            logger.warning(
                                "Leitura do stream RTSP falhou; nova tentativa em %s s.",
                                self._reconnect_seconds,
                            )
                            break
                        with self._lock:
                            self._latest_frame = frame
                            self._frame_sequence += 1
                            self._connected = True
            except Exception:
                with self._lock:
                    self._last_error = (
                        "Erro ao ligar à Câmara Tapo. A tentar novamente..."
                    )
                logger.exception("Erro ao ler o stream RTSP.")
            finally:
                with self._lock:
                    self._connected = False
                    self._latest_frame = None
                if capture is not None:
                    capture.release()

            if not self._stop_event.is_set():
                self._stop_event.wait(self._reconnect_seconds)


def _webcam_backend() -> int:
    """Escolhe o backend do OpenCV adequado ao sistema operativo."""
    if sys.platform.startswith("win"):
        return cv2.CAP_DSHOW
    if sys.platform.startswith("linux"):
        return getattr(cv2, "CAP_V4L2", cv2.CAP_ANY)
    if sys.platform == "darwin":
        return getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY)
    return cv2.CAP_ANY


class WebcamReader:
    """Lê a webcam predefinida do PC numa thread dedicada."""

    def __init__(self, camera_index: int = 0, reconnect_seconds: int = 5) -> None:
        if reconnect_seconds < 1:
            raise ValueError("reconnect_seconds tem de ser pelo menos 1.")
        self._camera_index = camera_index
        self._reconnect_seconds = reconnect_seconds
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_sequence = 0
        self._connected = False
        self._last_error: Optional[str] = None

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def start(self) -> "WebcamReader":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop,
            name="webcam-reader",
            daemon=True,
        )
        self._thread.start()
        return self

    def get_frame(self) -> Optional[np.ndarray]:
        frame, _ = self.get_frame_with_sequence()
        return frame

    def get_frame_with_sequence(
        self,
    ) -> tuple[Optional[np.ndarray], Optional[int]]:
        with self._lock:
            if self._latest_frame is None:
                return None, None
            return self._latest_frame.copy(), self._frame_sequence

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "A thread da webcam não terminou dentro de %.1f segundos.", timeout
                )
        with self._lock:
            self._connected = False
            self._latest_frame = None

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            capture: Optional[cv2.VideoCapture] = None
            try:
                capture = cv2.VideoCapture(
                    self._camera_index,
                    _webcam_backend(),
                )
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not capture.isOpened():
                    with self._lock:
                        self._connected = False
                        self._latest_frame = None
                        self._last_error = (
                            "Não foi possível ligar à Câmara do PC."
                        )
                    logger.warning("Não foi possível abrir a webcam.")
                else:
                    with self._lock:
                        self._connected = True
                        self._last_error = None
                    logger.info("Ligação à webcam estabelecida.")
                    while not self._stop_event.is_set():
                        success, frame = capture.read()
                        if not success or frame is None:
                            with self._lock:
                                self._connected = False
                                self._latest_frame = None
                                self._last_error = (
                                    "A leitura da Câmara do PC falhou."
                                )
                            break
                        with self._lock:
                            self._latest_frame = frame
                            self._frame_sequence += 1
                            self._connected = True
                            self._last_error = None
            except Exception:
                with self._lock:
                    self._connected = False
                    self._latest_frame = None
                    self._last_error = "Erro ao ligar à Câmara do PC."
                logger.exception("Erro ao ler a webcam.")
            finally:
                if capture is not None:
                    capture.release()
            if not self._stop_event.is_set():
                self._stop_event.wait(self._reconnect_seconds)


class CameraManager:
    """Alterna em execução entre a Tapo configurada e a webcam do PC."""

    VALID_SOURCES = ("tapo", "webcam")

    def __init__(
        self,
        rtsp_url: str,
        webcam_index: int = 0,
        reconnect_seconds: int = 5,
    ) -> None:
        self._rtsp_url = rtsp_url
        self._webcam_index = webcam_index
        self._reconnect_seconds = reconnect_seconds
        self._switch_lock = threading.Lock()
        self._reader_lock = threading.Lock()
        self._source = "tapo"
        self._reader = RTSPReader(
            rtsp_url,
            reconnect_seconds=reconnect_seconds,
        )

    @property
    def source(self) -> str:
        with self._switch_lock:
            return self._source

    def start(self) -> "CameraManager":
        with self._reader_lock:
            self._reader.start()
        return self

    def stop(self, timeout: float = 10.0) -> None:
        with self._reader_lock:
            self._reader.stop(timeout=timeout)

    def get_frame_with_sequence(
        self,
    ) -> tuple[Optional[np.ndarray], Optional[int]]:
        with self._reader_lock:
            reader = self._reader
        return reader.get_frame_with_sequence()

    def get_frame(self) -> Optional[np.ndarray]:
        frame, _ = self.get_frame_with_sequence()
        return frame

    def switch_source(self, source: str) -> dict[str, object]:
        if source not in self.VALID_SOURCES:
            raise ValueError(
                "Fonte inválida. Use 'tapo' ou 'webcam'."
            )
        with self._switch_lock:
            if source == self._source:
                return self.status()

            with self._reader_lock:
                old_reader = self._reader
                if source == "tapo":
                    new_reader = RTSPReader(
                        self._rtsp_url,
                        reconnect_seconds=self._reconnect_seconds,
                    )
                else:
                    new_reader = WebcamReader(
                        camera_index=self._webcam_index,
                        reconnect_seconds=self._reconnect_seconds,
                    )
                self._source = source
                self._reader = new_reader

            old_reader.stop(timeout=5)
            new_reader.start()
            return self.status()

    def status(self) -> dict[str, object]:
        with self._reader_lock:
            reader = self._reader
            source = self._source
        connected = reader.connected
        error = reader.last_error
        if not connected and error is None:
            error = (
                "A ligar à Câmara Tapo..."
                if source == "tapo"
                else "A ligar à Câmara do PC..."
            )
        return {
            "source": source,
            "source_label": (
                "Câmara Tapo" if source == "tapo" else "Câmara do PC"
            ),
            "connected": connected,
            "error": error,
        }
