"""Captura amostras faciais e regista um aluno localmente."""

import argparse
from datetime import datetime
from pathlib import Path
import sys

import cv2
import face_recognition


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_settings
from app.database import Database
from app.face_engine import FaceEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regista um aluno ou professor e captura amostras faciais."
    )
    parser.add_argument("--nome", help="Nome; se omitido, será pedido.")
    parser.add_argument("--cargo", choices=("Aluno", "Professor"))
    parser.add_argument("--ano", help="Ano/nível do aluno.")
    parser.add_argument("--curso", help="Curso do aluno.")
    parser.add_argument("--turma", help="Turma (campo legado, opcional).")
    parser.add_argument("--idade", type=int, help="Idade opcional, em anos.")
    parser.add_argument("--telefone", help="Telefone opcional.")
    parser.add_argument("--email", help="Email opcional.")
    parser.add_argument("--hora-entrada", help="Hora prevista (HH:MM), opcional.")
    parser.add_argument("--hora-saida", help="Hora prevista (HH:MM), opcional.")
    parser.add_argument("--imagens", type=int, default=5, help="Amostras a capturar.")
    parser.add_argument(
        "--camera-index", type=int, default=0, help="Índice da câmara local."
    )
    return parser.parse_args()


def _optional_time(value: str | None, prompt: str) -> str | None:
    time_value = value if value is not None else input(prompt)
    if not time_value.strip():
        return None
    try:
        return datetime.strptime(time_value.strip(), "%H:%M").strftime("%H:%M")
    except ValueError as error:
        raise ValueError("As horas previstas têm de estar no formato HH:MM.") from error


def main() -> int:
    args = parse_args()
    nome = (args.nome or input("Nome: ")).strip()
    if not nome:
        raise ValueError("O nome não pode estar vazio.")
    cargo = (args.cargo or input("Cargo (Aluno/Professor): ")).strip().title()
    if cargo not in {"Aluno", "Professor"}:
        raise ValueError("O cargo tem de ser Aluno ou Professor.")
    if cargo == "Aluno":
        ano = args.ano if args.ano is not None else input("Ano/nível: ")
        curso = args.curso if args.curso is not None else input("Curso: ")
        ano = ano.strip()
        curso = curso.strip()
        if not ano or not curso:
            raise ValueError("Ano e curso são obrigatórios para alunos.")
    else:
        if args.ano or args.curso:
            raise ValueError("Ano e curso só se aplicam a alunos.")
        ano = None
        curso = None

    idade = args.idade
    if idade is None:
        age_text = input("Idade (opcional; Enter para omitir): ").strip()
        if age_text:
            try:
                idade = int(age_text)
            except ValueError as error:
                raise ValueError("A idade tem de ser um número inteiro.") from error
    if idade is not None and not 1 <= idade <= 120:
        raise ValueError("A idade tem de estar entre 1 e 120 anos.")

    telefone = args.telefone
    if telefone is None:
        telefone = input("Telefone (opcional; Enter para omitir): ")
    email = args.email
    if email is None:
        email = input("Email (opcional; Enter para omitir): ")
    hora_entrada = _optional_time(
        args.hora_entrada, "Hora prevista de entrada (HH:MM; opcional): "
    )
    hora_saida = _optional_time(
        args.hora_saida, "Hora prevista de saída (HH:MM; opcional): "
    )
    if args.imagens < 1:
        raise ValueError("--imagens tem de ser pelo menos 1.")

    camera = cv2.VideoCapture(args.camera_index)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(
            f"Não foi possível abrir a câmara local {args.camera_index}."
        )

    encodings = []
    try:
        while len(encodings) < args.imagens:
            success, frame = camera.read()
            if not success or frame is None:
                raise RuntimeError("Falha ao ler uma imagem da câmara local.")
            preview = frame.copy()
            cv2.putText(
                preview,
                f"Amostras: {len(encodings)}/{args.imagens} | ESPACO captura | Q termina",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow("Registo de aluno", preview)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print("Captura cancelada; não foi criado nenhum aluno.")
                return 1
            if key != ord(" "):
                continue

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb_frame, model="hog")
            if len(locations) != 1:
                print("A captura requer exatamente um rosto visível. Tenta novamente.")
                continue
            face_encodings = face_recognition.face_encodings(
                rgb_frame, known_face_locations=locations
            )
            if len(face_encodings) != 1:
                print("Não foi possível codificar o rosto. Tenta novamente.")
                continue
            encodings.append(face_encodings[0])
            print(f"Amostra {len(encodings)}/{args.imagens} capturada.")
    finally:
        camera.release()
        cv2.destroyAllWindows()

    settings = load_settings()
    database = Database(settings.db_path)
    pessoa_id = database.add_person_with_encodings(
        nome,
        cargo,
        [encoding.tolist() for encoding in encodings],
        turma=args.turma or "",
        ano=ano,
        curso=curso,
        idade=idade,
        telefone=telefone,
        email=email,
        hora_entrada_prevista=hora_entrada,
        hora_saida_prevista=hora_saida,
    )
    face_engine = FaceEngine(settings.encodings_path, settings.face_tolerance)
    face_engine.load_records(database.list_encodings())
    print(
        f"{cargo} {nome} (ID {pessoa_id}) registado com "
        f"{len(encodings)} amostras."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
