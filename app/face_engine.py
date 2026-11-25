"""Interface de reconhecimento facial para o motor local."""

from dataclasses import dataclass
import logging
from pathlib import Path
import pickle
from typing import Optional

import face_recognition
import numpy as np


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FaceMatch:
    aluno_id: Optional[int]
    nome: str
    turma: str
    distancia: Optional[float]
    confianca: float
    face_location: tuple[int, int, int, int]


class FaceEngine:
    """Deteta rostos e compara-os com encodings conhecidos."""

    def __init__(self, encodings_path: Path | str, tolerance: float = 0.5) -> None:
        if not 0.0 < tolerance <= 1.0:
            raise ValueError("tolerance tem de ser superior a 0 e, no máximo, 1.")
        self.encodings_path = Path(encodings_path)
        self.tolerance = tolerance
        self._known_encodings: list[np.ndarray] = []
        self._students: list[tuple[int, str, str]] = []

    def load_encodings(self) -> int:
        """Carrega o ficheiro local; devolve o número de amostras válidas."""
        if not self.encodings_path.exists():
            logger.info("Ainda não existe ficheiro de encodings em %s.", self.encodings_path)
            self._known_encodings.clear()
            self._students.clear()
            return 0

        with self.encodings_path.open("rb") as encoding_file:
            payload = pickle.load(encoding_file)
        return self._replace_encodings(payload)

    def load_records(self, records: list[dict[str, object]]) -> int:
        """Atualiza o motor a partir da BD e sincroniza o ficheiro pickle."""
        count = self._replace_encodings(records)
        self.save_encodings()
        return count

    def _replace_encodings(self, payload: object) -> int:
        if not isinstance(payload, list):
            raise ValueError("O ficheiro de encodings tem um formato inválido.")

        known_encodings: list[np.ndarray] = []
        students: list[tuple[int, str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Uma entrada do ficheiro de encodings é inválida.")
            try:
                student_id = int(item["aluno_id"])
                name = str(item["nome"])
                class_name = str(item.get("turma", ""))
                encoding = np.asarray(item["encoding"], dtype=np.float64)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    "Uma entrada do ficheiro de encodings é inválida."
                ) from error
            if encoding.ndim != 1 or encoding.size == 0:
                raise ValueError("Foi encontrado um encoding facial inválido.")
            known_encodings.append(encoding)
            students.append((student_id, name, class_name))

        self._known_encodings = known_encodings
        self._students = students
        logger.info("Foram carregados %d encodings faciais.", len(known_encodings))
        return len(known_encodings)

    def add_encoding(
        self, aluno_id: int, nome: str, turma: str, encoding: np.ndarray
    ) -> None:
        """Adiciona uma amostra e guarda o conjunto atualizado em formato pickle."""
        vector = np.asarray(encoding, dtype=np.float64)
        if vector.ndim != 1 or vector.size == 0:
            raise ValueError("O encoding facial tem de ser um vetor não vazio.")
        self._known_encodings.append(vector)
        self._students.append((aluno_id, nome, turma))
        self.save_encodings()

    def save_encodings(self) -> None:
        """Grava os encodings atomicamente para evitar ficheiros incompletos."""
        self.encodings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "aluno_id": student_id,
                "nome": name,
                "turma": class_name,
                "encoding": encoding.tolist(),
            }
            for encoding, (student_id, name, class_name) in zip(
                self._known_encodings, self._students
            )
        ]
        temporary_path = self.encodings_path.with_suffix(
            self.encodings_path.suffix + ".tmp"
        )
        with temporary_path.open("wb") as encoding_file:
            pickle.dump(payload, encoding_file, protocol=pickle.HIGHEST_PROTOCOL)
        temporary_path.replace(self.encodings_path)

    def recognize(self, frame: np.ndarray) -> list[FaceMatch]:
        """Encontra rostos no frame e associa cada um ao encoding mais próximo."""
        rgb_frame = np.ascontiguousarray(frame[:, :, ::-1])
        locations = face_recognition.face_locations(rgb_frame, model="hog")
        encodings = face_recognition.face_encodings(
            rgb_frame, known_face_locations=locations
        )
        matches: list[FaceMatch] = []

        for location, encoding in zip(locations, encodings):
            if not self._known_encodings:
                matches.append(
                    FaceMatch(None, "Desconhecido", "", None, 0.0, location)
                )
                continue

            distances = face_recognition.face_distance(
                self._known_encodings, encoding
            )
            best_index = int(np.argmin(distances))
            distance = float(distances[best_index])
            if distance <= self.tolerance:
                student_id, name, class_name = self._students[best_index]
                matches.append(
                    FaceMatch(
                        student_id,
                        name,
                        class_name,
                        distance,
                        max(0.0, 1.0 - distance),
                        location,
                    )
                )
            else:
                matches.append(
                    FaceMatch(
                        None,
                        "Desconhecido",
                        "",
                        distance,
                        0.0,
                        location,
                    )
                )
        return matches
