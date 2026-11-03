"""Cliente do Google Drive atrás de uma interface pequena (o Drive só recebe cópias, D14).

`ClienteDrive` é o contrato que o resto do sistema usa; `ClienteDriveGoogle` o cumpre com o cliente
oficial `google-api-python-client` e uma conta de serviço (sem tokens que expiram quando alguém sai
da empresa). Nos testes entra um Drive simulado em memória, com as mesmas regras do real: o Drive
**aceita vários itens com o mesmo nome** na mesma pasta.
"""

import io
from abc import ABC, abstractmethod

from googleapiclient.errors import HttpError

ESCOPO = "https://www.googleapis.com/auth/drive"
TIPO_PASTA = "application/vnd.google-apps.folder"
STATUS_TEMPORARIOS = {408, 429, 500, 502, 503, 504}


class ErroDrive(Exception):
    """Falha no Drive. `mensagem` é para o usuário; `detalhe` é técnico e sem segredos."""

    def __init__(self, mensagem, *, detalhe="", temporario=True, nao_encontrado=False):
        """Guarda a explicação, o detalhe curto e se vale tentar de novo."""
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhe = detalhe[:300]
        self.temporario = temporario
        self.nao_encontrado = nao_encontrado


class ClienteDrive(ABC):
    """Operações mínimas de que a cópia ao Drive precisa."""

    @abstractmethod
    def obter_pasta(self, pasta_id):
        """`{"id", "nome", "pode_escrever"}` da pasta, ou `ErroDrive` se não existe/não é pasta."""

    @abstractmethod
    def listar(self, pai_id, nome=None, somente_pastas=False):
        """Itens (`id`, `nome`, `propriedades`) da pasta, opcionalmente só os de certo nome."""

    @abstractmethod
    def criar_pasta(self, nome, pai_id):
        """Cria a pasta e devolve o ID."""

    @abstractmethod
    def enviar(self, nome, pai_id, conteudo, tipo_mime, propriedades=None):
        """Cria o arquivo e devolve o ID. `propriedades` marcam a quem o arquivo pertence."""

    @abstractmethod
    def atualizar(self, file_id, conteudo, tipo_mime):
        """Troca o conteúdo do arquivo existente (sem criar outro)."""


def _escapar(texto):
    return texto.replace("\\", "\\\\").replace("'", "\\'")


def criar_servico_drive(conta_servico):
    """Cliente `drive v3` autenticado como a conta de serviço."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credenciais = service_account.Credentials.from_service_account_info(
        conta_servico, scopes=[ESCOPO]
    )
    return build("drive", "v3", credentials=credenciais, cache_discovery=False)


class ClienteDriveGoogle(ClienteDrive):
    """Implementação sobre o `google-api-python-client` (`servico` é injetável nos testes)."""

    def __init__(self, servico):
        """Guarda o cliente `drive v3` já autenticado."""
        self._servico = servico

    @staticmethod
    def _traduzir(erro):
        status = erro.resp.status
        if status in STATUS_TEMPORARIOS:
            return ErroDrive(
                "O Google Drive está indisponível ou limitou o uso agora. O sistema tenta de novo "
                "sozinho.",
                detalhe=f"Drive HTTP {status}",
            )
        if status == 404:
            return ErroDrive(
                "O Google Drive não encontrou a pasta ou o arquivo. Confira o ID da pasta e se a "
                "conta de serviço tem acesso a ela.",
                detalhe="Drive HTTP 404",
                temporario=False,
                nao_encontrado=True,
            )
        return ErroDrive(
            "O Google Drive recusou o acesso. Compartilhe a pasta com a conta de serviço como "
            "Editor (ou adicione-a ao Drive compartilhado).",
            detalhe=f"Drive HTTP {status}",
            temporario=False,
        )

    def _executar(self, pedido):
        try:
            return pedido.execute()
        except HttpError as erro:
            raise self._traduzir(erro) from None
        except OSError as erro:
            raise ErroDrive(
                "Não foi possível falar com o Google Drive agora. O sistema tenta de novo sozinho.",
                detalhe=type(erro).__name__,
            ) from None

    def obter_pasta(self, pasta_id):
        """Confere que o ID é uma pasta com acesso de escrita e devolve o nome."""
        dados = self._executar(
            self._servico.files().get(
                fileId=pasta_id,
                fields="id,name,mimeType,capabilities(canAddChildren)",
                supportsAllDrives=True,
            )
        )
        if dados.get("mimeType") != TIPO_PASTA:
            raise ErroDrive(
                "O ID informado é de um arquivo, não de uma pasta.",
                detalhe="mimeType diferente de pasta",
                temporario=False,
            )
        return {
            "id": dados["id"],
            "nome": dados.get("name", ""),
            "pode_escrever": bool(dados.get("capabilities", {}).get("canAddChildren")),
        }

    def listar(self, pai_id, nome=None, somente_pastas=False):
        """Lista os itens da pasta (com `name`/tipo opcionais), todas as páginas."""
        consulta = [f"'{_escapar(pai_id)}' in parents", "trashed = false"]
        if nome is not None:
            consulta.append(f"name = '{_escapar(nome)}'")
        if somente_pastas:
            consulta.append(f"mimeType = '{TIPO_PASTA}'")
        itens, pagina = [], None
        while True:
            resposta = self._executar(
                self._servico.files().list(
                    q=" and ".join(consulta),
                    fields="nextPageToken,files(id,name,appProperties)",
                    pageSize=100,
                    pageToken=pagina,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora="allDrives",
                )
            )
            itens += [
                {"id": f["id"], "nome": f["name"], "propriedades": f.get("appProperties", {})}
                for f in resposta.get("files", [])
            ]
            pagina = resposta.get("nextPageToken")
            if not pagina:
                return itens

    def criar_pasta(self, nome, pai_id):
        """Cria a subpasta e devolve o ID."""
        corpo = {"name": nome, "mimeType": TIPO_PASTA, "parents": [pai_id]}
        dados = self._executar(
            self._servico.files().create(body=corpo, fields="id", supportsAllDrives=True)
        )
        return dados["id"]

    def enviar(self, nome, pai_id, conteudo, tipo_mime, propriedades=None):
        """Envia o arquivo à pasta e devolve o ID."""
        from googleapiclient.http import MediaIoBaseUpload

        corpo = {"name": nome, "parents": [pai_id], "appProperties": propriedades or {}}
        midia = MediaIoBaseUpload(io.BytesIO(conteudo), mimetype=tipo_mime, resumable=False)
        dados = self._executar(
            self._servico.files().create(
                body=corpo, media_body=midia, fields="id", supportsAllDrives=True
            )
        )
        return dados["id"]

    def atualizar(self, file_id, conteudo, tipo_mime):
        """Sobrescreve o conteúdo do arquivo (mesmo `fileId`)."""
        from googleapiclient.http import MediaIoBaseUpload

        midia = MediaIoBaseUpload(io.BytesIO(conteudo), mimetype=tipo_mime, resumable=False)
        self._executar(
            self._servico.files().update(
                fileId=file_id, media_body=midia, fields="id", supportsAllDrives=True
            )
        )
