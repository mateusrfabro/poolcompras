"""Limpa todas as rodadas e registros dependentes do DB de dev.

Preserva: Usuario, Lanchonete, Fornecedor, Produto.
Zera: Rodada e tudo que tem FK pra Rodada (cascata manual em ordem segura).

Uso:
    python scripts/limpar_rodadas_dev.py            # mostra contagens e pede ENTER
    python scripts/limpar_rodadas_dev.py --yes      # executa sem prompt

IMPORTANTE: roda com FLASK_ENV padrao (development). Nao roda contra
producao sem FLASK_ENV/APP_CONFIG apontando pra 'development' — o
assert no inicio bloqueia se DB uri for de producao.
"""
import os
import sys
from pathlib import Path

# Garante que app/ esta no path independente de onde o script eh invocado
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SECRET_KEY", "dev-cleanup")

from app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    Rodada, ItemPedido, Cotacao, RodadaProduto, ParticipacaoRodada,
    AvaliacaoRodada, EventoRodada, SubmissaoCotacao, NotaNegociacao,
)


# Ordem de delete respeitando FKs (filhos primeiro).
# NotaNegociacao.submissao_id -> SubmissaoCotacao
# AvaliacaoRodada -> (rodada, lanchonete, fornecedor)
# EventoRodada -> (rodada, lanchonete, ator)
# ItemPedido -> (rodada, lanchonete, produto)
# Cotacao -> (rodada, fornecedor, produto)
# RodadaProduto -> (rodada, produto)
# ParticipacaoRodada -> (rodada, lanchonete)
# SubmissaoCotacao -> (rodada, fornecedor)
# Rodada
ORDEM = [
    NotaNegociacao,
    AvaliacaoRodada,
    EventoRodada,
    ItemPedido,
    Cotacao,
    RodadaProduto,
    ParticipacaoRodada,
    SubmissaoCotacao,
    Rodada,
]


def _resumo():
    return [(m.__name__, db.session.query(m).count()) for m in ORDEM]


def main(argv):
    app = create_app("development")
    with app.app_context():
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        assert "poolcompras.db" in uri and "poolcompras-test" not in uri, (
            f"Abortado: URI inesperada: {uri}"
        )
        print(f"DB: {uri}")

        print("\nAntes da limpeza:")
        for nome, n in _resumo():
            print(f"  {nome:20s} {n}")

        if "--yes" not in argv:
            resposta = input("\nConfirma limpeza? [s/N] ").strip().lower()
            if resposta != "s":
                print("Cancelado.")
                return 1

        total = 0
        for m in ORDEM:
            n = db.session.query(m).delete(synchronize_session=False)
            print(f"  deletado {m.__name__:20s} = {n}")
            total += n
        db.session.commit()

        print(f"\nTotal de linhas deletadas: {total}")
        print("\nDepois da limpeza:")
        for nome, n in _resumo():
            print(f"  {nome:20s} {n}")
        print("\nProduto / Fornecedor / Lanchonete / Usuario preservados.")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
