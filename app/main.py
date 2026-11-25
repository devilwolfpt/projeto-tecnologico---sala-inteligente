"""Servidor FastAPI, processamento de vídeo e endpoints do dashboard."""

from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
import logging
from pathlib import Path
import threading
import time
from typing import AsyncIterator, Optional

import cv2
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
import numpy as np

from app.camera import CameraManager
from app.config import Settings, load_settings
from app.database import Database
from app.face_engine import FaceEngine
from app.logic import AttendanceLogic


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
INDEX_PATH = Path(__file__).parent / "templates" / "index.html"
PREVIEW_MAX_WIDTH = 960
PREVIEW_INTERVAL_SECONDS = 1 / 12


@dataclass
class Runtime:
    settings: Settings
    database: Database
    camera: CameraManager
    face_engine: FaceEngine
    attendance: AttendanceLogic
    stop_event: threading.Event
    processor: Optional[threading.Thread] = None


def _processing_loop(runtime: Runtime) -> None:
    last_seen_sequence = 0
    last_processed_sequence = 0
    process_every = runtime.settings.process_every_n_frames
    while not runtime.stop_event.is_set():
        frame, sequence = runtime.camera.get_frame_with_sequence()
        if frame is None or sequence is None:
            runtime.stop_event.wait(0.2)
            continue

        if sequence == last_seen_sequence:
            runtime.stop_event.wait(0.01)
            continue
        last_seen_sequence = sequence
        if sequence - last_processed_sequence < process_every:
            continue
        last_processed_sequence = sequence

        try:
            matches = runtime.face_engine.recognize(frame)
            for match in matches:
                if match.aluno_id is None:
                    continue
                try:
                    runtime.attendance.register(
                        match.aluno_id, match.confianca, frame
                    )
                except Exception:
                    logger.exception(
                        "Não foi possível registar a presença do aluno %s.",
                        match.aluno_id,
                    )
        except Exception:
            logger.exception("Falha no processamento de um frame.")
            runtime.stop_event.wait(0.2)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    database = Database(settings.db_path)
    face_engine = FaceEngine(settings.encodings_path, settings.face_tolerance)
    face_engine.load_records(database.list_encodings())
    camera = CameraManager(
        settings.rtsp_url,
        webcam_index=settings.pc_camera_index,
        reconnect_seconds=settings.camera_reconnect_seconds,
    )
    attendance = AttendanceLogic(
        database,
        settings.snapshots_path,
        debounce_seconds=settings.debounce_seconds,
        min_interval_minutes=settings.min_interval_minutes,
    )
    runtime = Runtime(
        settings=settings,
        database=database,
        camera=camera,
        face_engine=face_engine,
        attendance=attendance,
        stop_event=threading.Event(),
    )
    application.state.runtime = runtime
    camera.start()
    runtime.processor = threading.Thread(
        target=_processing_loop,
        args=(runtime,),
        name="face-processor",
        daemon=True,
    )
    runtime.processor.start()
    logger.info("Servidor de presenças iniciado.")
    try:
        yield
    finally:
        runtime.stop_event.set()
        camera.stop()
        if runtime.processor is not None:
            runtime.processor.join(timeout=10)
            if runtime.processor.is_alive():
                logger.warning("A thread de processamento não terminou a tempo.")
        logger.info("Servidor de presenças parado.")


app = FastAPI(title="Controlo de presenças Tapo", lifespan=lifespan)


def _runtime() -> Runtime:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="A aplicação ainda não iniciou.")
    return runtime


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(INDEX_PATH.read_text(encoding="utf-8"))


@app.get("/video_feed")
def video_feed() -> StreamingResponse:
    runtime = _runtime()

    def stream_frames():
        last_sequence: Optional[int] = None
        while not runtime.stop_event.is_set():
            frame, sequence = runtime.camera.get_frame_with_sequence()
            if frame is None or sequence is None:
                time.sleep(0.05)
                continue
            if sequence == last_sequence:
                time.sleep(0.01)
                continue
            last_sequence = sequence

            height, width = frame.shape[:2]
            if width > PREVIEW_MAX_WIDTH:
                preview_height = round(height * PREVIEW_MAX_WIDTH / width)
                frame = cv2.resize(
                    frame,
                    (PREVIEW_MAX_WIDTH, preview_height),
                    interpolation=cv2.INTER_AREA,
                )
            success, encoded = cv2.imencode(".jpg", frame)
            if not success:
                logger.error("Não foi possível codificar um frame para MJPEG.")
                time.sleep(PREVIEW_INTERVAL_SECONDS)
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + encoded.tobytes()
                + b"\r\n"
            )
            time.sleep(PREVIEW_INTERVAL_SECONDS)

    return StreamingResponse(
        stream_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/registos")
def api_registos(
    data: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None, ge=1, le=1000),
) -> list[dict[str, object]]:
    if data is not None:
        from datetime import date

        try:
            parsed_date = date.fromisoformat(data)
        except ValueError as error:
            raise HTTPException(
                status_code=422, detail="data tem de estar no formato YYYY-MM-DD."
            ) from error
        if parsed_date.isoformat() != data:
            raise HTTPException(
                status_code=422, detail="data tem de estar no formato YYYY-MM-DD."
            )
    runtime = _runtime()
    records = runtime.database.list_registrations(date=data, limit=limit)
    return [asdict(record) for record in records]


@app.get("/api/presentes")
def api_presentes() -> list[dict[str, object]]:
    runtime = _runtime()
    return [
        {
            "id": person.id,
            "nome": person.nome,
            "cargo": person.cargo,
            "ano": person.ano,
            "curso": person.curso,
            "turma": person.turma,
            "hora_entrada_prevista": person.hora_entrada_prevista,
            "hora_saida_prevista": person.hora_saida_prevista,
        }
        for person in runtime.database.list_present_people()
    ]


@app.get("/api/camera/status")
def api_camera_status() -> dict[str, object]:
    return _runtime().camera.status()


@app.post("/api/camera/source")
def api_camera_source(payload: dict[str, object]) -> dict[str, object]:
    source = payload.get("source")
    if not isinstance(source, str):
        raise HTTPException(
            status_code=422,
            detail="Indique 'source' com o valor 'tapo' ou 'webcam'.",
        )
    if source not in CameraManager.VALID_SOURCES:
        raise HTTPException(
            status_code=422,
            detail="Fonte inválida. Use 'tapo' ou 'webcam'.",
        )
    try:
        return _runtime().camera.switch_source(source)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
