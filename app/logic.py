"""Regras de negócio para entradas, saídas e debounce persistente."""

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Optional
from uuid import uuid4

import cv2
import numpy as np

from app.database import Database, Registration


logger = logging.getLogger(__name__)


class AttendanceLogic:
    """Decide o tipo de registo usando o último evento persistido do aluno."""

    def __init__(
        self,
        database: Database,
        snapshots_path: Path | str,
        debounce_seconds: int = 30,
        min_interval_minutes: int = 10,
    ) -> None:
        if debounce_seconds < 0:
            raise ValueError("debounce_seconds não pode ser negativo.")
        if min_interval_minutes < 0:
            raise ValueError("min_interval_minutes não pode ser negativo.")
        self.database = database
        self.snapshots_path = Path(snapshots_path)
        self.debounce_seconds = debounce_seconds
        self.min_interval = timedelta(minutes=min_interval_minutes)
        self._lock = threading.Lock()

    def register(
        self, aluno_id: int, confianca: float, frame: np.ndarray
    ) -> Optional[Registration]:
        """Regista ENTRADA/SAIDA ou devolve None se o evento estiver em debounce."""
        with self._lock:
            now = datetime.now(timezone.utc)
            latest = self.database.get_latest_registration(aluno_id)
            if latest is not None:
                latest_at = datetime.fromisoformat(latest.timestamp)
                if latest_at.tzinfo is None:
                    latest_at = latest_at.replace(tzinfo=timezone.utc)
                elapsed = now - latest_at
                if elapsed < timedelta(seconds=self.debounce_seconds):
                    logger.info(
                        "Registo ignorado para aluno %s: dentro do debounce da BD.",
                        aluno_id,
                    )
                    return None

                if latest.tipo == "ENTRADA":
                    if elapsed < self.min_interval:
                        logger.info(
                            "Registo ignorado para aluno %s: ainda não passou o "
                            "intervalo mínimo para saída.",
                            aluno_id,
                        )
                        return None
                    tipo = "SAIDA"
                else:
                    tipo = "ENTRADA"
            else:
                tipo = "ENTRADA"

            self.snapshots_path.mkdir(parents=True, exist_ok=True)
            filename = (
                f"{now.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex}.jpg"
            )
            snapshot_path = self.snapshots_path / filename
            if not cv2.imwrite(str(snapshot_path), frame):
                raise OSError(f"Não foi possível guardar o snapshot: {snapshot_path}")

            timestamp = now.isoformat(timespec="microseconds")
            try:
                registration_id = self.database.add_registration(
                    aluno_id=aluno_id,
                    tipo=tipo,
                    confianca=confianca,
                    snapshot_path=str(snapshot_path),
                    timestamp=timestamp,
                )
            except sqlite3.Error:
                snapshot_path.unlink(missing_ok=True)
                raise

            logger.info(
                "%s registada para aluno %s (confiança %.3f).",
                tipo,
                aluno_id,
                confianca,
            )
            return Registration(
                id=registration_id,
                aluno_id=aluno_id,
                tipo=tipo,
                timestamp=timestamp,
                confianca=confianca,
                snapshot_path=str(snapshot_path),
            )
