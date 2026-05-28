"""Tests do /health enriquecido (app_version + migration_head).

Cenario que motiva: pipeline /deploy_aggron do Ademar precisa confirmar
que container subiu na versao certa E que migration aplicou (cenario
bug 1+2 de 2026-05-27 — codigo novo, migration desatualizada).
"""
from app.services import app_info


def test_health_retorna_200_com_db_ok(client):
    """Smoke: /health em condicao normal retorna 200 + JSON com chaves esperadas."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    # Chaves de observabilidade — pipeline do Ademar depende delas.
    assert "app_version" in data
    assert "migration_head" in data


def test_health_app_version_nao_esta_vazio(client):
    """app_version sempre retorna algo (SHA, env, ou 'unknown'). Nunca None/vazio."""
    resp = client.get("/health")
    version = resp.get_json()["app_version"]
    assert isinstance(version, str)
    assert len(version) > 0


def test_health_migration_head_em_db_sem_alembic_table(client):
    """conftest usa db.create_all() (nao roda migrations) -> tabela
    alembic_version nao existe. migration_head deve retornar 'none' ou 'unknown',
    nunca quebrar o endpoint."""
    resp = client.get("/health")
    head = resp.get_json()["migration_head"]
    assert head in ("none", "unknown")
    # Importante: nao quebrou (status_code 200)
    assert resp.status_code == 200


def test_app_version_respeita_env_override(client, monkeypatch):
    """APP_VERSION env injetada pelo Dockerfile sobrescreve git SHA."""
    monkeypatch.setenv("APP_VERSION", "deploy-2026-05-28-abc123")
    app_info._reset_cache_for_tests()

    resp = client.get("/health")
    assert resp.get_json()["app_version"] == "deploy-2026-"  # truncado em 12

    # Limpa cache pra nao afetar outros testes
    app_info._reset_cache_for_tests()
