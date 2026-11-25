"""Acesso à base de dados SQLite local."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Iterator, Optional


logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Person:
    id: int
    nome: str
    turma: str
    ativo: bool
    created_at: str
    cargo: str = "Aluno"
    ano: Optional[str] = None
    curso: Optional[str] = None
    idade: Optional[int] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    hora_entrada_prevista: Optional[str] = None
    hora_saida_prevista: Optional[str] = None


Student = Person


@dataclass(frozen=True)
class Registration:
    id: int
    aluno_id: int
    tipo: str
    timestamp: str
    confianca: float
    snapshot_path: str
    nome: Optional[str] = None
    turma: Optional[str] = None
    cargo: Optional[str] = None
    ano: Optional[str] = None
    curso: Optional[str] = None


class Database:
    """Cria o esquema local e disponibiliza operações tipadas sobre as tabelas."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Cria as tabelas necessárias se ainda não existirem."""
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS alunos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    turma TEXT NOT NULL DEFAULT '',
                    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
                    created_at TEXT NOT NULL,
                    cargo TEXT NOT NULL DEFAULT 'Aluno'
                        CHECK (cargo IN ('Aluno', 'Professor')),
                    ano TEXT,
                    curso TEXT,
                    idade INTEGER CHECK (idade IS NULL OR idade BETWEEN 1 AND 120),
                    telefone TEXT,
                    email TEXT,
                    hora_entrada_prevista TEXT,
                    hora_saida_prevista TEXT
                );

                CREATE TABLE IF NOT EXISTS encodings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
                    encoding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS registos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER NOT NULL REFERENCES alunos(id),
                    tipo TEXT NOT NULL CHECK (tipo IN ('ENTRADA', 'SAIDA')),
                    timestamp TEXT NOT NULL,
                    confianca REAL NOT NULL,
                    snapshot_path TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_registos_aluno_timestamp
                    ON registos (aluno_id, timestamp DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_registos_timestamp
                    ON registos (timestamp DESC);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(alunos)").fetchall()
            }
            migrations = {
                "cargo": (
                    "TEXT NOT NULL DEFAULT 'Aluno' "
                    "CHECK (cargo IN ('Aluno', 'Professor'))"
                ),
                "ano": "TEXT",
                "curso": "TEXT",
                "idade": "INTEGER CHECK (idade IS NULL OR idade BETWEEN 1 AND 120)",
                "telefone": "TEXT",
                "email": "TEXT",
                "hora_entrada_prevista": "TEXT",
                "hora_saida_prevista": "TEXT",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE alunos ADD COLUMN {name} {definition}"
                    )
        logger.info("Base de dados inicializada em %s.", self.db_path)

    @staticmethod
    def _normalize_time(value: Optional[str], field: str) -> Optional[str]:
        if value is None or not value.strip():
            return None
        try:
            return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M")
        except ValueError as error:
            raise ValueError(f"{field} tem de estar no formato HH:MM.") from error

    @classmethod
    def _normalize_profile_fields(
        cls,
        cargo: str,
        ano: Optional[str],
        curso: Optional[str],
        idade: Optional[int],
        telefone: Optional[str],
        email: Optional[str],
        hora_entrada_prevista: Optional[str],
        hora_saida_prevista: Optional[str],
    ) -> tuple[
        str,
        Optional[str],
        Optional[str],
        Optional[int],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
    ]:
        cargo = cargo.strip().title()
        if cargo not in {"Aluno", "Professor"}:
            raise ValueError("O cargo tem de ser Aluno ou Professor.")
        if idade is not None and (
            isinstance(idade, bool) or not 1 <= idade <= 120
        ):
            raise ValueError("A idade tem de estar entre 1 e 120 anos.")

        ano_value = ano.strip() if ano and ano.strip() else None
        curso_value = curso.strip() if curso and curso.strip() else None
        if cargo == "Professor" and (ano_value or curso_value):
            raise ValueError("Ano e curso só se aplicam a perfis de Aluno.")
        return (
            cargo,
            ano_value,
            curso_value,
            idade,
            telefone.strip() if telefone and telefone.strip() else None,
            email.strip() if email and email.strip() else None,
            cls._normalize_time(hora_entrada_prevista, "Hora prevista de entrada"),
            cls._normalize_time(hora_saida_prevista, "Hora prevista de saída"),
        )

    def add_student(self, nome: str, turma: str = "") -> int:
        """Cria um aluno ativo e devolve o respetivo identificador."""
        nome = nome.strip()
        if not nome:
            raise ValueError("O nome do aluno não pode estar vazio.")
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO alunos (nome, turma, created_at) VALUES (?, ?, ?)",
                (nome, turma.strip(), _utc_now()),
            )
            return int(cursor.lastrowid)

    def add_person_with_encodings(
        self,
        nome: str,
        cargo: str,
        encodings: list[list[float]],
        *,
        turma: str = "",
        ano: Optional[str] = None,
        curso: Optional[str] = None,
        idade: Optional[int] = None,
        telefone: Optional[str] = None,
        email: Optional[str] = None,
        hora_entrada_prevista: Optional[str] = None,
        hora_saida_prevista: Optional[str] = None,
    ) -> int:
        """Cria um perfil e guarda as amostras faciais na mesma transação."""
        nome = nome.strip()
        if not nome:
            raise ValueError("O nome não pode estar vazio.")
        if not encodings or any(not encoding for encoding in encodings):
            raise ValueError("É necessário fornecer encodings faciais não vazios.")
        (
            cargo,
            ano_value,
            curso_value,
            idade,
            telefone_value,
            email_value,
            entrada_value,
            saida_value,
        ) = self._normalize_profile_fields(
            cargo,
            ano,
            curso,
            idade,
            telefone,
            email,
            hora_entrada_prevista,
            hora_saida_prevista,
        )
        created_at = _utc_now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO alunos (
                    nome, turma, ativo, created_at, cargo, ano, curso, idade,
                    telefone, email, hora_entrada_prevista, hora_saida_prevista
                )
                VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    nome,
                    turma.strip(),
                    created_at,
                    cargo,
                    ano_value,
                    curso_value,
                    idade,
                    telefone_value,
                    email_value,
                    entrada_value,
                    saida_value,
                ),
            )
            pessoa_id = int(cursor.lastrowid)
            connection.executemany(
                "INSERT INTO encodings (aluno_id, encoding_json, created_at) "
                "VALUES (?, ?, ?)",
                [
                    (pessoa_id, json.dumps(encoding), created_at)
                    for encoding in encodings
                ],
            )
            return pessoa_id

    def add_student_with_encodings(
        self, nome: str, turma: str, encodings: list[list[float]]
    ) -> int:
        """Cria o aluno e guarda todas as amostras numa única transação."""
        pessoa_id = self.add_person_with_encodings(
            nome,
            "Aluno",
            encodings,
            turma=turma,
        )
        return pessoa_id

    def get_person(self, pessoa_id: int) -> Optional[Person]:
        query = """
            SELECT id, nome, turma, ativo, created_at, cargo, ano, curso, idade,
                   telefone, email, hora_entrada_prevista, hora_saida_prevista
            FROM alunos
            WHERE id = ?
        """
        with self._connection() as connection:
            row = connection.execute(query, (pessoa_id,)).fetchone()
        if row is None:
            return None
        return Person(
            id=row["id"],
            nome=row["nome"],
            turma=row["turma"],
            ativo=bool(row["ativo"]),
            created_at=row["created_at"],
            cargo=row["cargo"],
            ano=row["ano"],
            curso=row["curso"],
            idade=row["idade"],
            telefone=row["telefone"],
            email=row["email"],
            hora_entrada_prevista=row["hora_entrada_prevista"],
            hora_saida_prevista=row["hora_saida_prevista"],
        )

    def update_person_profile(
        self,
        pessoa_id: int,
        *,
        cargo: str,
        ano: Optional[str] = None,
        curso: Optional[str] = None,
        idade: Optional[int] = None,
        telefone: Optional[str] = None,
        email: Optional[str] = None,
        hora_entrada_prevista: Optional[str] = None,
        hora_saida_prevista: Optional[str] = None,
    ) -> None:
        """Atualiza o perfil sem alterar os encodings ou os registos de presença."""
        (
            cargo,
            ano_value,
            curso_value,
            idade,
            telefone_value,
            email_value,
            entrada_value,
            saida_value,
        ) = self._normalize_profile_fields(
            cargo,
            ano,
            curso,
            idade,
            telefone,
            email,
            hora_entrada_prevista,
            hora_saida_prevista,
        )
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE alunos
                SET cargo = ?, ano = ?, curso = ?, idade = ?, telefone = ?,
                    email = ?, hora_entrada_prevista = ?, hora_saida_prevista = ?
                WHERE id = ?
                """,
                (
                    cargo,
                    ano_value,
                    curso_value,
                    idade,
                    telefone_value,
                    email_value,
                    entrada_value,
                    saida_value,
                    pessoa_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Não existe um perfil com o ID {pessoa_id}.")

    def list_people(self, active_only: bool = True) -> list[Person]:
        query = (
            "SELECT id, nome, turma, ativo, created_at, cargo, ano, curso, idade, "
            "telefone, email, hora_entrada_prevista, hora_saida_prevista FROM alunos"
        )
        if active_only:
            query += " WHERE ativo = 1"
        query += " ORDER BY nome COLLATE NOCASE, id"
        with self._connection() as connection:
            rows = connection.execute(query).fetchall()
        return [
            Person(
                id=row["id"],
                nome=row["nome"],
                turma=row["turma"],
                ativo=bool(row["ativo"]),
                created_at=row["created_at"],
                cargo=row["cargo"],
                ano=row["ano"],
                curso=row["curso"],
                idade=row["idade"],
                telefone=row["telefone"],
                email=row["email"],
                hora_entrada_prevista=row["hora_entrada_prevista"],
                hora_saida_prevista=row["hora_saida_prevista"],
            )
            for row in rows
        ]

    def list_students(self, active_only: bool = True) -> list[Person]:
        return [
            person for person in self.list_people(active_only) if person.cargo == "Aluno"
        ]

    def add_encoding(self, aluno_id: int, encoding: list[float]) -> int:
        """Guarda uma amostra facial serializada como JSON na base de dados."""
        if not encoding:
            raise ValueError("O encoding facial não pode estar vazio.")
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO encodings (aluno_id, encoding_json, created_at) "
                "VALUES (?, ?, ?)",
                (aluno_id, json.dumps(encoding), _utc_now()),
            )
            return int(cursor.lastrowid)

    def list_encodings(self, active_only: bool = True) -> list[dict[str, object]]:
        """Devolve todos os encodings guardados e os dados do respetivo aluno."""
        query = (
            "SELECT e.aluno_id, a.nome, a.turma, a.cargo, a.ano, a.curso, "
            "e.encoding_json "
            "FROM encodings e JOIN alunos a ON a.id = e.aluno_id"
        )
        if active_only:
            query += " WHERE a.ativo = 1"
        query += " ORDER BY e.id"
        with self._connection() as connection:
            rows = connection.execute(query).fetchall()
        return [
            {
                "aluno_id": row["aluno_id"],
                "nome": row["nome"],
                "turma": row["turma"],
                "cargo": row["cargo"],
                "ano": row["ano"],
                "curso": row["curso"],
                "encoding": json.loads(row["encoding_json"]),
            }
            for row in rows
        ]

    def get_latest_registration(self, aluno_id: int) -> Optional[Registration]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, aluno_id, tipo, timestamp, confianca, snapshot_path
                FROM registos
                WHERE aluno_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """,
                (aluno_id,),
            ).fetchone()
        if row is None:
            return None
        return Registration(
            id=row["id"],
            aluno_id=row["aluno_id"],
            tipo=row["tipo"],
            timestamp=row["timestamp"],
            confianca=row["confianca"],
            snapshot_path=row["snapshot_path"],
        )

    def add_registration(
        self,
        aluno_id: int,
        tipo: str,
        confianca: float,
        snapshot_path: str,
        timestamp: Optional[str] = None,
    ) -> int:
        """Insere uma entrada ou saída e devolve o identificador do registo."""
        if tipo not in {"ENTRADA", "SAIDA"}:
            raise ValueError("O tipo de registo tem de ser ENTRADA ou SAIDA.")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO registos
                    (aluno_id, tipo, timestamp, confianca, snapshot_path)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    aluno_id,
                    tipo,
                    timestamp or _utc_now(),
                    confianca,
                    snapshot_path,
                ),
            )
            return int(cursor.lastrowid)

    def list_registrations(
        self, date: Optional[str] = None, limit: Optional[int] = None
    ) -> list[Registration]:
        """Lista registos, opcionalmente filtrados por dia UTC."""
        query = (
            "SELECT r.id, r.aluno_id, r.tipo, r.timestamp, r.confianca, "
            "r.snapshot_path, a.nome, a.turma, a.cargo, a.ano, a.curso "
            "FROM registos r JOIN alunos a ON a.id = r.aluno_id"
        )
        parameters: list[object] = []
        if date is not None:
            query += " WHERE substr(r.timestamp, 1, 10) = ?"
            parameters.append(date)
        query += " ORDER BY r.timestamp DESC, r.id DESC"
        if limit is not None:
            if limit < 1:
                raise ValueError("limit tem de ser pelo menos 1.")
            query += " LIMIT ?"
            parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            Registration(
                id=row["id"],
                aluno_id=row["aluno_id"],
                tipo=row["tipo"],
                timestamp=row["timestamp"],
                confianca=row["confianca"],
                snapshot_path=row["snapshot_path"],
                nome=row["nome"],
                turma=row["turma"],
                cargo=row["cargo"],
                ano=row["ano"],
                curso=row["curso"],
            )
            for row in rows
        ]

    def list_present_people(self) -> list[Person]:
        """Devolve pessoas cujo último registo é uma entrada."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT a.id, a.nome, a.turma, a.ativo, a.created_at, a.cargo,
                       a.ano, a.curso, a.idade, a.telefone, a.email,
                       a.hora_entrada_prevista, a.hora_saida_prevista
                FROM alunos a
                WHERE a.ativo = 1
                  AND EXISTS (
                      SELECT 1
                      FROM registos r
                      WHERE r.aluno_id = a.id
                        AND r.tipo = 'ENTRADA'
                        AND NOT EXISTS (
                            SELECT 1
                            FROM registos newer
                            WHERE newer.aluno_id = r.aluno_id
                              AND (
                                  newer.timestamp > r.timestamp
                                  OR (
                                      newer.timestamp = r.timestamp
                                      AND newer.id > r.id
                                  )
                              )
                        )
                  )
                ORDER BY a.nome COLLATE NOCASE, a.id
                """
            ).fetchall()
        return [
            Person(
                id=row["id"],
                nome=row["nome"],
                turma=row["turma"],
                ativo=bool(row["ativo"]),
                created_at=row["created_at"],
                cargo=row["cargo"],
                ano=row["ano"],
                curso=row["curso"],
                idade=row["idade"],
                telefone=row["telefone"],
                email=row["email"],
                hora_entrada_prevista=row["hora_entrada_prevista"],
                hora_saida_prevista=row["hora_saida_prevista"],
            )
            for row in rows
        ]

    def list_present_students(self) -> list[Person]:
        return [
            person
            for person in self.list_present_people()
            if person.cargo == "Aluno"
        ]
