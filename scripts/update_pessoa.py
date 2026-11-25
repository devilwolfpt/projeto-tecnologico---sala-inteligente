"""Atualiza dados de perfil sem voltar a capturar o rosto."""

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_settings
from app.database import Database, Person


def _ask_optional(label: str, current: str | None) -> str | None:
    current_text = current or ""
    value = input(
        f"{label} [{current_text}] (Enter mantém; - limpa): "
    ).strip()
    if not value:
        return current
    if value == "-":
        return None
    return value


def _edit_profile(database: Database, person: Person) -> None:
    cargo = _ask_optional("Cargo (Aluno/Professor)", person.cargo)
    if cargo not in {"Aluno", "Professor"}:
        raise ValueError("O cargo tem de ser Aluno ou Professor.")

    if cargo == "Aluno":
        ano = _ask_optional("Ano/nível", person.ano)
        curso = _ask_optional("Curso", person.curso)
        if not ano or not curso:
            raise ValueError("Ano e curso são obrigatórios para alunos.")
    else:
        ano = None
        curso = None

    age_text = _ask_optional(
        "Idade (opcional)", str(person.idade) if person.idade is not None else None
    )
    try:
        idade = int(age_text) if age_text else None
    except ValueError as error:
        raise ValueError("A idade tem de ser um número inteiro.") from error

    telefone = _ask_optional("Telefone (opcional)", person.telefone)
    email = _ask_optional("Email (opcional)", person.email)
    hora_entrada = _ask_optional(
        "Hora prevista de entrada (HH:MM)", person.hora_entrada_prevista
    )
    hora_saida = _ask_optional(
        "Hora prevista de saída (HH:MM)", person.hora_saida_prevista
    )
    database.update_person_profile(
        person.id,
        cargo=cargo,
        ano=ano,
        curso=curso,
        idade=idade,
        telefone=telefone,
        email=email,
        hora_entrada_prevista=hora_entrada,
        hora_saida_prevista=hora_saida,
    )
    print(f"Perfil de {person.nome} (ID {person.id}) atualizado.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Atualiza o perfil de um aluno ou professor existente."
    )
    parser.add_argument("--id", type=int, help="ID do perfil a atualizar.")
    args = parser.parse_args()
    pessoa_id = args.id
    if pessoa_id is None:
        pessoa_id = int(input("ID do perfil: "))

    database = Database(load_settings().db_path)
    person = database.get_person(pessoa_id)
    if person is None:
        raise ValueError(f"Não existe um perfil com o ID {pessoa_id}.")
    _edit_profile(database, person)


if __name__ == "__main__":
    main()
