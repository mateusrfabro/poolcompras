"""Testes dos filtros Jinja customizados."""


def test_brl_filter_formatacao_milhar(app):
    brl = app.jinja_env.filters["brl"]
    assert brl(1234.56) == "R$ 1.234,56"
    assert brl(1234567.89) == "R$ 1.234.567,89"
    assert brl(0) == "R$ 0,00"
    assert brl(12.5) == "R$ 12,50"
    assert brl(None) == "—"


def test_qtd_filter_inteiro_vs_decimal(app):
    qtd = app.jinja_env.filters["qtd"]
    assert qtd(5) == "5"
    assert qtd(5.0) == "5"
    assert qtd(10.6) == "10,6"
    assert qtd(None) == "-"


def test_fmt_un_pluralizacao(app):
    fmt = app.jinja_env.filters["fmt_un"]
    # Singular
    assert fmt(1, "fardo") == "1 fardo"
    assert fmt(1, "unidade") == "1 unidade"
    # Plural
    assert fmt(5, "fardo") == "5 fardos"
    assert fmt(2, "caixa") == "2 caixas"
    assert fmt(10, "litro") == "10 litros"
    # Simbolos invariaveis
    assert fmt(1, "kg") == "1 kg"
    assert fmt(10, "kg") == "10 kg"
    assert fmt(1.5, "kg") == "1,5 kg"
    # Zero pluraliza
    assert fmt(0, "fardo") == "0 fardos"


def test_status_label(app):
    sl = app.jinja_env.filters["status_label"]
    assert sl("aberta") == "Em aberto"
    assert sl("finalizada") == "Finalizada"
    assert sl("cancelada") == "Cancelada"
    assert sl("desconhecido") == "desconhecido"  # fallback
    assert sl(None) == "—"
