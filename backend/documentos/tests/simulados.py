"""Serviços externos SIMULADOS dos testes de documentos: Drive, SMTP, Gmail e Microsoft Graph.

Nada sai para a rede e nada aqui é credencial real: a chave RSA da "conta de serviço" nasce na hora.
O Drive simulado segue a regra que mais importa do real: aceita **vários itens com o mesmo nome**
na mesma pasta, e a listagem pode atrasar (como a indexação do Drive).
"""

import itertools
import json
import smtplib
import threading
import time
from functools import cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from documentos.services.drive.cliente import TIPO_PASTA, ClienteDrive, ErroDrive


@cache
def _chave_pem():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def conta_de_servico_json(email="conta-teste@projeto-ficticio.iam.gserviceaccount.com"):
    """JSON de conta de serviço FICTÍCIA (a chave privada é gerada em código, nunca versionada)."""
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "projeto-ficticio",
            "private_key_id": "0" * 40,
            "private_key": _chave_pem(),
            "client_email": email,
            "client_id": "1234567890",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


SEGREDO_DE_TESTE = "segredo-ficticio-do-teste-4471"


# --- Drive ---------------------------------------------------------------------------------


class DriveSimulado(ClienteDrive):
    """Drive em memória. Duplicatas de nome são permitidas; a indexação da listagem pode atrasar."""

    def __init__(
        self,
        raiz_id="RAIZ",
        raiz_nome="Notas Fiscais",
        pode_escrever=True,
        latencia=0.0,
        atraso_de_indexacao=0.0,
    ):
        """Cria o Drive com a pasta raiz (e, opcionalmente, latência e atraso de indexação)."""
        self.itens = {raiz_id: {"id": raiz_id, "nome": raiz_nome, "pai": None, "tipo": TIPO_PASTA}}
        self.pode_escrever = pode_escrever
        self.raiz_id = raiz_id
        self.latencia = latencia  # demora de cada criação, para expor concorrência
        self.atraso_de_indexacao = (
            atraso_de_indexacao  # segundos até um item novo aparecer em `listar`
        )
        self.falhas = []  # exceções a levantar nas próximas chamadas de escrita
        self.chamadas = []
        self._contador = itertools.count(1)
        self._cadeado = threading.Lock()

    # -- consultas de teste --
    def pastas(self, nome=None):
        """Pastas (exceto a raiz) com o nome informado."""
        return [
            i
            for i in self.itens.values()
            if i["tipo"] == TIPO_PASTA
            and i["pai"] is not None
            and (nome is None or i["nome"] == nome)
        ]

    def arquivos(self):
        """Todos os arquivos (não pastas)."""
        return [i for i in self.itens.values() if i["tipo"] != TIPO_PASTA]

    def caminho_de(self, item_id):
        """Caminho legível do item a partir da raiz."""
        partes = []
        while item_id and item_id != self.raiz_id:
            item = self.itens[item_id]
            partes.append(item["nome"])
            item_id = item["pai"]
        return "/".join(reversed(partes))

    def _falha(self):
        if self.falhas:
            raise self.falhas.pop(0)

    # -- contrato --
    def obter_pasta(self, pasta_id):
        """Pasta pelo ID (ou erro de não encontrada)."""
        self.chamadas.append(("obter_pasta", pasta_id))
        item = self.itens.get(pasta_id)
        if item is None:
            raise ErroDrive(
                "O Google Drive não encontrou a pasta ou o arquivo.",
                temporario=False, nao_encontrado=True,
            )  # fmt: skip
        if item["tipo"] != TIPO_PASTA:
            raise ErroDrive("O ID informado é de um arquivo, não de uma pasta.", temporario=False)
        return {"id": item["id"], "nome": item["nome"], "pode_escrever": self.pode_escrever}

    def listar(self, pai_id, nome=None, somente_pastas=False):
        """Itens da pasta, ignorando os criados há menos que o atraso de indexação."""
        self.chamadas.append(("listar", pai_id, nome))
        agora = time.monotonic()
        with self._cadeado:
            return [
                {"id": i["id"], "nome": i["nome"], "propriedades": dict(i.get("propriedades", {}))}
                for i in self.itens.values()
                if i["pai"] == pai_id
                and (nome is None or i["nome"] == nome)
                and (not somente_pastas or i["tipo"] == TIPO_PASTA)
                and agora - i["criado"] >= self.atraso_de_indexacao
            ]

    def _criar(self, nome, pai_id, tipo, conteudo=b"", propriedades=None):
        self._falha()
        if pai_id not in self.itens:
            raise ErroDrive("Pasta não encontrada.", temporario=False, nao_encontrado=True)
        time.sleep(self.latencia)
        with self._cadeado:
            item_id = f"ID{next(self._contador)}"
            self.itens[item_id] = {
                "id": item_id, "nome": nome, "pai": pai_id, "tipo": tipo, "conteudo": conteudo,
                "propriedades": propriedades or {}, "criado": time.monotonic(),
            }  # fmt: skip
        return item_id

    def criar_pasta(self, nome, pai_id):
        """Cria a pasta (o nome pode repetir)."""
        self.chamadas.append(("criar_pasta", nome, pai_id))
        return self._criar(nome, pai_id, TIPO_PASTA)

    def enviar(self, nome, pai_id, conteudo, tipo_mime, propriedades=None):
        """Cria o arquivo (o nome pode repetir)."""
        self.chamadas.append(("enviar", nome, pai_id))
        return self._criar(nome, pai_id, tipo_mime, conteudo, propriedades)

    def atualizar(self, file_id, conteudo, tipo_mime):
        """Troca o conteúdo; arquivo inexistente vira erro de não encontrado."""
        self.chamadas.append(("atualizar", file_id))
        self._falha()
        if file_id not in self.itens:
            raise ErroDrive("Arquivo não encontrado.", temporario=False, nao_encontrado=True)
        self.itens[file_id]["conteudo"] = conteudo


# --- SMTP ----------------------------------------------------------------------------------


class ServidorSmtpFalso:
    """Substitui `smtplib.SMTP`: grava o que foi pedido e pode falhar de propósito."""

    def __init__(self, falha=None):
        """`falha` é a exceção levantada em `send_message` (em `login`, se for de autenticação)."""
        self.falha = falha
        self.eventos = []
        self.mensagens = []

    def __call__(self):
        return self

    def __enter__(self):
        self.eventos.append("conectou")
        return self

    def __exit__(self, *_):
        self.eventos.append("fechou")

    def starttls(self):
        self.eventos.append("starttls")

    def login(self, usuario, senha):
        self.eventos.append(("login", usuario, senha))
        if isinstance(self.falha, smtplib.SMTPAuthenticationError):
            raise self.falha

    def send_message(self, mime, from_addr, to_addrs):
        if self.falha and not isinstance(self.falha, smtplib.SMTPAuthenticationError):
            raise self.falha
        self.mensagens.append({"mime": mime, "de": from_addr, "para": list(to_addrs)})


# --- Microsoft Graph -----------------------------------------------------------------------


class RespostaFalsa:
    """Resposta HTTP mínima."""

    def __init__(self, status_code, corpo=None):
        """Guarda o status e o corpo JSON."""
        self.status_code = status_code
        self._corpo = corpo or {}

    def json(self):
        return self._corpo


class SessaoGraphFalsa:
    """Substitui `requests.Session`: primeiro o token, depois o `sendMail`."""

    def __init__(self, status_token=200, status_envio=202):
        """Define as respostas do token e do envio."""
        self.status_token, self.status_envio = status_token, status_envio
        self.chamadas = []

    def post(self, url, data=None, json=None, headers=None, timeout=None):
        self.chamadas.append({"url": url, "data": data, "json": json, "headers": headers or {}})
        if "oauth2/v2.0/token" in url:
            return RespostaFalsa(self.status_token, {"access_token": "token-ficticio"})
        return RespostaFalsa(self.status_envio)


class ServicoGmailFalso:
    """Substitui o cliente `gmail v1`: `users().messages().send(...).execute()`."""

    def __init__(self, erro=None):
        """`erro` é levantado no `execute`."""
        self.erro = erro
        self.enviados = []

    def users(self):
        return self

    def messages(self):
        return self

    def send(self, userId, body):  # noqa: N803 - assinatura da API do Google
        self._ultimo = (userId, body)
        return self

    def execute(self):
        if self.erro:
            raise self.erro
        self.enviados.append(self._ultimo)
        return {"id": "msg-ficticia"}
