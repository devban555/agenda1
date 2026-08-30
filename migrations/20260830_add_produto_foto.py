#!/usr/bin/env python3

import argparse
import sqlite3
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Adiciona de forma idempotente a coluna "
            "foto_arquivo à tabela produto."
        )
    )

    parser.add_argument(
        "--db",
        default="agendamento/instance/local.db",
        help="Caminho do banco SQLite."
    )

    args = parser.parse_args()

    arquivo = Path(args.db).resolve()

    if not arquivo.is_file():
        print(
            f"ERRO: banco não encontrado: {arquivo}",
            file=sys.stderr
        )
        return 1

    db = sqlite3.connect(
        str(arquivo),
        timeout=30
    )

    db.execute(
        "PRAGMA busy_timeout = 30000"
    )

    try:
        integridade_antes = db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        print(
            "integrity_check antes:",
            integridade_antes
        )

        if integridade_antes != "ok":
            print(
                "ERRO: banco não está íntegro.",
                file=sys.stderr
            )
            return 2

        tabela = db.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name='produto'
        """).fetchone()

        if not tabela:
            print(
                "ERRO: tabela produto não encontrada.",
                file=sys.stderr
            )
            return 3

        colunas = {
            row[1]
            for row in db.execute(
                "PRAGMA table_info(produto)"
            )
        }

        if "foto_arquivo" in colunas:
            print(
                "foto_arquivo já existe. "
                "Nenhuma alteração necessária."
            )
        else:
            db.execute("""
                ALTER TABLE produto
                ADD COLUMN foto_arquivo VARCHAR(255)
            """)

            db.commit()

            print(
                "Coluna foto_arquivo adicionada."
            )

        colunas_depois = {
            row[1]
            for row in db.execute(
                "PRAGMA table_info(produto)"
            )
        }

        if "foto_arquivo" not in colunas_depois:
            print(
                "ERRO: coluna não encontrada "
                "após migração.",
                file=sys.stderr
            )
            return 4

        integridade_depois = db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        print(
            "integrity_check depois:",
            integridade_depois
        )

        print(
            "produtos:",
            db.execute(
                "SELECT COUNT(*) FROM produto"
            ).fetchone()[0]
        )

        if integridade_depois != "ok":
            return 5

        print("Migração: OK")
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
