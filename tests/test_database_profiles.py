import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.database import Database
from app.main import api_presentes, app


class DatabaseProfileTests(unittest.TestCase):
    def test_existing_database_migrates_without_losing_student_data(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE alunos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    turma TEXT NOT NULL DEFAULT '',
                    ativo INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE encodings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER NOT NULL REFERENCES alunos(id),
                    encoding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE registos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aluno_id INTEGER NOT NULL REFERENCES alunos(id),
                    tipo TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    confianca REAL NOT NULL,
                    snapshot_path TEXT NOT NULL
                );
                INSERT INTO alunos (id, nome, turma, created_at)
                    VALUES (1, 'Aluno antigo', '1A', '2026-01-01T08:00:00+00:00');
                INSERT INTO encodings (aluno_id, encoding_json, created_at)
                    VALUES (1, '[0.1, 0.2]', '2026-01-01T08:00:00+00:00');
                INSERT INTO registos
                    (aluno_id, tipo, timestamp, confianca, snapshot_path)
                    VALUES (1, 'ENTRADA', '2026-01-01T08:01:00+00:00', 0.9, 'old.jpg');
                """
            )
            connection.commit()
            connection.close()

            database = Database(path)
            person = database.get_person(1)

            self.assertIsNotNone(person)
            assert person is not None
            self.assertEqual(person.cargo, "Aluno")
            self.assertEqual(person.turma, "1A")
            self.assertEqual(len(database.list_encodings()), 1)
            self.assertEqual(database.get_latest_registration(1).tipo, "ENTRADA")

    def test_student_and_teacher_profiles_and_schedule_update(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Database(Path(temporary_directory) / "profiles.db")
            student_id = database.add_person_with_encodings(
                "Ana",
                "Aluno",
                [[0.1, 0.2]],
                ano="1.º",
                curso="TPI",
                idade=16,
                telefone="912345678",
                email="ana@example.org",
                hora_entrada_prevista="8:00",
                hora_saida_prevista="17:00",
            )
            teacher_id = database.add_person_with_encodings(
                "Rui",
                "Professor",
                [[0.3, 0.4]],
                hora_entrada_prevista="09:00",
            )

            student = database.get_person(student_id)
            teacher = database.get_person(teacher_id)
            self.assertEqual(student.cargo, "Aluno")
            self.assertEqual(student.hora_entrada_prevista, "08:00")
            self.assertEqual(student.hora_saida_prevista, "17:00")
            self.assertEqual(teacher.cargo, "Professor")
            self.assertIsNone(teacher.ano)
            self.assertEqual(len(database.list_students()), 1)
            self.assertEqual(len(database.list_people()), 2)

            database.add_registration(student_id, "ENTRADA", 0.9, "")
            attendance_record = database.list_registrations(limit=1)[0]
            self.assertEqual(attendance_record.cargo, "Aluno")
            self.assertEqual(attendance_record.ano, "1.º")
            self.assertEqual(attendance_record.curso, "TPI")

            database.update_person_profile(
                teacher_id,
                cargo="Professor",
                idade=42,
                telefone="",
                email="rui@example.org",
                hora_entrada_prevista="08:30",
                hora_saida_prevista=None,
            )
            updated = database.get_person(teacher_id)
            self.assertEqual(updated.idade, 42)
            self.assertEqual(updated.hora_entrada_prevista, "08:30")
            self.assertEqual(updated.email, "rui@example.org")
            self.assertEqual(len(database.list_encodings()), 2)

    def test_invalid_profiles_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Database(Path(temporary_directory) / "profiles.db")
            with self.assertRaises(ValueError):
                database.add_person_with_encodings(
                    "Professor",
                    "Professor",
                    [[0.1]],
                    ano="1.º",
                )
            with self.assertRaises(ValueError):
                database.add_person_with_encodings(
                    "Aluno",
                    "Aluno",
                    [[0.1]],
                    idade=0,
                )
            with self.assertRaises(ValueError):
                database.add_person_with_encodings(
                    "Aluno",
                    "Aluno",
                    [[0.1]],
                    hora_entrada_prevista="oito",
                )

    def test_presentes_includes_both_roles_without_private_contact_data(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Database(Path(temporary_directory) / "profiles.db")
            student_id = database.add_person_with_encodings(
                "Ana",
                "Aluno",
                [[0.1]],
                ano="1.º",
                curso="TPI",
                telefone="912345678",
                email="ana@example.org",
                idade=16,
            )
            teacher_id = database.add_person_with_encodings(
                "Rui",
                "Professor",
                [[0.2]],
            )
            database.add_registration(student_id, "ENTRADA", 0.9, "")
            database.add_registration(teacher_id, "ENTRADA", 0.9, "")

            runtime = SimpleNamespace(database=database)
            with patch.object(app.state, "runtime", runtime, create=True):
                present = api_presentes()

            self.assertEqual({person["cargo"] for person in present}, {"Aluno", "Professor"})
            self.assertTrue(all("telefone" not in person for person in present))
            self.assertTrue(all("email" not in person for person in present))
            self.assertTrue(all("idade" not in person for person in present))


if __name__ == "__main__":
    unittest.main()
