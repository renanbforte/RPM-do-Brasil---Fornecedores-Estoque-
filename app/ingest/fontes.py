"""
Abstração da FONTE dos arquivos.

O resto do pipeline (extração → Claude → gravação atômica) não deve saber se
os bytes vêm de uma pasta local ou do Google Drive. Aqui ficam:

- ArquivoRef        : referência leve a um arquivo (id, nome, mime, tamanho...)
- FonteArquivos     : interface (listar / baixar)
- FonteLocal        : lê de uma pasta local (dev/teste)
- FonteGoogleDrive  : lê de uma pasta do Drive via conta de serviço (produção)

Trocar de fonte é só mudar FONTE no .env.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core import config

# Extensões de arquivo que o pipeline sabe extrair
EXTENSOES_SUPORTADAS = {".xlsx", ".xls", ".csv", ".txt", ".docx"}

# MIME types nativos do Google e para que exportá-los ao baixar
_EXPORT_NATIVOS = {
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
}


@dataclass
class ArquivoRef:
    """Referência a um arquivo na fonte, sem carregar o conteúdo."""
    id: str                       # caminho (local) ou fileId (Drive)
    nome: str                     # nome do arquivo, ex: "Cópia de ACME.xlsx"
    mime: str | None = None
    tamanho: int | None = None
    modificado_em: str | None = None

    @property
    def extensao(self) -> str:
        return Path(self.nome).suffix.lower()


@runtime_checkable
class FonteArquivos(Protocol):
    def listar(self) -> list[ArquivoRef]:
        """Lista os arquivos suportados disponíveis na fonte."""
        ...

    def baixar(self, ref: ArquivoRef) -> bytes:
        """Baixa o conteúdo bruto (bytes) do arquivo."""
        ...


def hash_bytes(conteudo: bytes) -> str:
    """SHA-256 do conteúdo — usado para detectar arquivo idêntico já processado."""
    return hashlib.sha256(conteudo).hexdigest()


# ==========================================================================
# FONTE LOCAL
# ==========================================================================
class FonteLocal:
    """Lê arquivos de uma pasta local (simula o Drive em dev/teste)."""

    def __init__(self, pasta: str | None = None) -> None:
        self.pasta = Path(pasta or config.PASTA_ENTRADA)

    def listar(self) -> list[ArquivoRef]:
        if not self.pasta.exists():
            return []
        refs: list[ArquivoRef] = []
        for p in sorted(self.pasta.iterdir()):
            if p.is_file() and p.suffix.lower() in EXTENSOES_SUPORTADAS:
                st = p.stat()
                refs.append(ArquivoRef(
                    id=str(p.resolve()),
                    nome=p.name,
                    tamanho=st.st_size,
                    modificado_em=str(int(st.st_mtime)),
                ))
        return refs

    def baixar(self, ref: ArquivoRef) -> bytes:
        return Path(ref.id).read_bytes()


# ==========================================================================
# FONTE GOOGLE DRIVE (conta de serviço)
# ==========================================================================
class FonteGoogleDrive:
    """
    Lê arquivos de uma pasta do Google Drive usando uma conta de serviço.
    Requer que a pasta esteja COMPARTILHADA com o e-mail da conta de serviço
    e que a Google Drive API esteja ativada no projeto.
    """

    _ESCOPO = ["https://www.googleapis.com/auth/drive.readonly"]

    def __init__(self, folder_id: str | None = None, credenciais: str | None = None) -> None:
        self.folder_id = folder_id or config.GDRIVE_FOLDER_ID
        self.cred_path = credenciais or config.GOOGLE_APPLICATION_CREDENTIALS
        if not self.folder_id:
            raise RuntimeError("GDRIVE_FOLDER_ID não configurado no .env")
        if not self.cred_path or not Path(self.cred_path).exists():
            raise RuntimeError(
                f"Credencial da conta de serviço não encontrada: {self.cred_path}")
        self._service = self._construir_service()

    def _construir_service(self):
        # imports locais para não exigir as libs quando FONTE=local
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        cred = service_account.Credentials.from_service_account_file(
            self.cred_path, scopes=self._ESCOPO)
        return build("drive", "v3", credentials=cred, cache_discovery=False)

    def listar(self) -> list[ArquivoRef]:
        refs: list[ArquivoRef] = []
        page_token = None
        query = f"'{self.folder_id}' in parents and trashed = false"
        while True:
            resp = self._service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []):
                nome = f["name"]
                mime = f.get("mimeType")
                # aceita arquivos por extensão OU nativos do Google (que exportamos)
                ext_ok = Path(nome).suffix.lower() in EXTENSOES_SUPORTADAS
                if ext_ok or mime in _EXPORT_NATIVOS:
                    refs.append(ArquivoRef(
                        id=f["id"], nome=nome, mime=mime,
                        tamanho=int(f["size"]) if f.get("size") else None,
                        modificado_em=f.get("modifiedTime"),
                    ))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return refs

    def baixar(self, ref: ArquivoRef) -> bytes:
        import io
        from googleapiclient.http import MediaIoBaseDownload

        if ref.mime in _EXPORT_NATIVOS:
            # arquivo nativo do Google → exporta para xlsx/docx
            export_mime, _ = _EXPORT_NATIVOS[ref.mime]
            req = self._service.files().export_media(fileId=ref.id, mimeType=export_mime)
        else:
            req = self._service.files().get_media(fileId=ref.id, supportsAllDrives=True)

        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()


def obter_fonte() -> FonteArquivos:
    """Fábrica: devolve a fonte configurada no .env (FONTE=local|drive)."""
    if config.FONTE == "drive":
        return FonteGoogleDrive()
    return FonteLocal()
