"""Lista os perfis ativos guardados na base de dados local."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_settings
from app.database import Database


def main() -> None:
    settings = load_settings()
    people = Database(settings.db_path).list_people()
    if not people:
        print("Ainda não existem perfis ativos.")
        return
    print(f"{'ID':>5}  {'NOME':<26}  {'CARGO':<10}  {'ANO':<8}  CURSO/TURMA")
    print("-" * 80)
    for person in people:
        year = person.ano or "—"
        course = person.curso or person.turma or "—"
        print(
            f"{person.id:>5}  {person.nome:<26}  {person.cargo:<10}  "
            f"{year:<8}  {course}"
        )


if __name__ == "__main__":
    main()
