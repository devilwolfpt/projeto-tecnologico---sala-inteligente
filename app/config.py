"""Carregamento da configuração da aplicação."""

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _project_path(value: str) -> Path:
    """Resolve caminhos relativos a partir da raiz do projeto."""
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    cam_ip: str
    cam_user: str
    cam_pass: str
    cam_rtsp_port: int
    cam_stream: str
    face_tolerance: float
    debounce_seconds: int
    min_interval_minutes: int
    process_every_n_frames: int
    db_path: Path
    encodings_path: Path
    snapshots_path: Path
    camera_reconnect_seconds: int = 5
    pc_camera_index: int = 0

    @property
    def rtsp_url(self) -> str:
        """Constrói o URL RTSP sem quebrar credenciais com caracteres especiais."""
        username = quote(self.cam_user, safe="")
        password = quote(self.cam_pass, safe="")
        stream = self.cam_stream.strip("/")
        return (
            f"rtsp://{username}:{password}@{self.cam_ip}:"
            f"{self.cam_rtsp_port}/{stream}"
        )


def load_settings() -> Settings:
    """Lê as variáveis de ambiente e aplica valores por omissão seguros."""
    settings = Settings(
        cam_ip=os.getenv("CAM_IP", "192.168.1.50"),
        cam_user=os.getenv("CAM_USER", "tapo_user"),
        cam_pass=os.getenv("CAM_PASS", "tapo_pass"),
        cam_rtsp_port=int(os.getenv("CAM_RTSP_PORT", "554")),
        cam_stream=os.getenv("CAM_STREAM", "stream1"),
        face_tolerance=float(os.getenv("FACE_TOLERANCE", "0.5")),
        debounce_seconds=int(os.getenv("DEBOUNCE_SECONDS", "30")),
        min_interval_minutes=int(os.getenv("MIN_INTERVAL_MINUTES", "10")),
        process_every_n_frames=int(os.getenv("PROCESS_EVERY_N_FRAMES", "5")),
        db_path=_project_path(os.getenv("DB_PATH", "data/presencas.db")),
        encodings_path=_project_path(
            os.getenv("ENCODINGS_PATH", "data/encodings.pkl")
        ),
        snapshots_path=_project_path(os.getenv("SNAPSHOTS_PATH", "snapshots")),
        camera_reconnect_seconds=int(os.getenv("CAMERA_RECONNECT_SECONDS", "5")),
        pc_camera_index=int(os.getenv("PC_CAMERA_INDEX", "0")),
    )
    if settings.cam_rtsp_port < 1 or settings.cam_rtsp_port > 65535:
        raise ValueError("CAM_RTSP_PORT tem de estar entre 1 e 65535.")
    if settings.process_every_n_frames < 1:
        raise ValueError("PROCESS_EVERY_N_FRAMES tem de ser pelo menos 1.")
    if settings.camera_reconnect_seconds < 1:
        raise ValueError("CAMERA_RECONNECT_SECONDS tem de ser pelo menos 1.")
    if settings.pc_camera_index < 0:
        raise ValueError("PC_CAMERA_INDEX tem de ser 0 ou superior.")
    return settings
