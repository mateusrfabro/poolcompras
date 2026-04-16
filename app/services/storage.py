"""
Abstracao de storage de arquivos (comprovantes de pagamento, etc.).

Permite trocar implementacao local <-> S3 sem mexer em rotas/templates.

Uso:
    storage = get_storage()
    key = storage.save(file_storage, subdir="comprovantes/2026/04", original_name="recibo.pdf")
    url = storage.url_for_key(key)         # link publico/assinado
    storage.delete(key)

A chave (`key`) e armazenada no banco. Sempre opaca: nao incluir info do cliente
no nome (use UUID + extensao validada).

A implementacao local guarda os arquivos em `instance/uploads/...`, FORA de `static/`,
para evitar execucao direta via URL. O download e servido por uma rota Flask
autenticada que consulta `storage.read(key)`.

ALLOWED_EXTENSIONS / ALLOWED_MIMES devem ser validados pelo CHAMADOR antes de salvar.
A camada de storage so se preocupa com persistencia.
"""
from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from typing import BinaryIO, Optional

from flask import current_app, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


class Storage(ABC):
    """Interface de storage. Implementacoes: LocalStorage, S3Storage (futuro)."""

    @abstractmethod
    def save(self, file: FileStorage, subdir: str, original_name: Optional[str] = None) -> str:
        """Persiste o arquivo. Retorna a 'key' opaca (caminho relativo) para guardar no DB."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Le o conteudo bruto. Levanta FileNotFoundError se nao existir."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove o arquivo. Idempotente: nao falha se ja foi removido."""

    @abstractmethod
    def url_for_key(self, key: str) -> str:
        """URL para servir o arquivo (rota interna autenticada na local; URL assinada na S3)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """True se o arquivo existe."""


class LocalStorage(Storage):
    """Storage em disco local. Base configurada via app.config['UPLOAD_FOLDER']."""

    def __init__(self, base_path: str):
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)

    def _resolve(self, key: str) -> str:
        """Resolve a key absoluta e bloqueia path traversal (defesa em profundidade)."""
        full = os.path.abspath(os.path.join(self.base_path, key))
        if not full.startswith(self.base_path + os.sep) and full != self.base_path:
            raise ValueError(f"Path traversal detectado: {key!r}")
        return full

    def save(self, file: FileStorage, subdir: str, original_name: Optional[str] = None) -> str:
        # Sanitiza extensao (so a extensao do nome original importa, nome eh substituido)
        nome_referencia = original_name or file.filename or "arquivo"
        nome_sanitizado = secure_filename(nome_referencia)
        _, ext = os.path.splitext(nome_sanitizado)
        ext = ext.lower() if ext else ""

        # Nome final = UUID + extensao validada (evita colisao e info-leak)
        nome_final = f"{uuid.uuid4().hex}{ext}"
        subdir_clean = subdir.strip("/").replace("..", "")  # bloqueia traversal no subdir
        rel_key = f"{subdir_clean}/{nome_final}" if subdir_clean else nome_final

        full_path = self._resolve(rel_key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        file.save(full_path)
        return rel_key

    def read(self, key: str) -> bytes:
        with open(self._resolve(key), "rb") as fh:
            return fh.read()

    def delete(self, key: str) -> None:
        try:
            os.remove(self._resolve(key))
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return os.path.isfile(self._resolve(key))

    def url_for_key(self, key: str) -> str:
        # Aponta para a rota Flask que serve com autenticacao + ownership check.
        # A rota e implementada na Fase 2 (uploads_bp).
        return url_for("uploads.servir", key=key)


_instance: Optional[Storage] = None


def init_storage(app) -> None:
    """Inicializa storage global a partir do config. Chamar dentro de create_app."""
    global _instance
    base = app.config.get("UPLOAD_FOLDER") or os.path.join(
        app.instance_path, "uploads"
    )
    _instance = LocalStorage(base)
    app.config["UPLOAD_FOLDER"] = base


def get_storage() -> Storage:
    """Retorna a instancia global de storage. Requer init_storage(app) chamado antes."""
    if _instance is None:
        raise RuntimeError(
            "Storage nao inicializado. Chame init_storage(app) em create_app()."
        )
    return _instance
