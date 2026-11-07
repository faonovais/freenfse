"""Parâmetros da instalação: leitura da linha de comando, perguntas e validação."""

import argparse
import ipaddress
import re
from dataclasses import dataclass, field
from pathlib import Path

RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parents[2]
_ROTULO = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMINIO = re.compile(rf"^(?=.{{1,253}}$){_ROTULO}(?:\.{_ROTULO})*$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CHAVE_PUBLICA_AGE = re.compile(r"^age1[0-9a-z]{58}$")
SUFIXOS_NAO_PUBLICOS = (".local", ".internal", ".lan", ".localhost", ".home", ".corp")


class ErroDeParametro(Exception):
    """Parâmetro inválido ou faltando; a mensagem diz o que corrigir (sem expor segredo)."""


@dataclass
class Parametros:
    """Tudo o que o instalador precisa saber."""

    modo: str
    dominio: str = ""
    email: str = ""
    porta_http: int = 80
    porta_https: int = 443
    dados: Path = Path("/var/lib/freenfse")
    tls: str = "nenhum"
    certificado: Path | None = None
    chave_privada: Path | None = None
    chave_publica_backup: str = ""
    gerar_chave_backup: Path | None = None
    email_master: str = ""
    criar_usuario_bi: bool = False
    simular: bool = False
    nao_interativo: bool = False
    repositorio: Path = RAIZ_DO_REPOSITORIO
    arquivo_env: Path | None = None
    pasta_systemd: Path = Path("/etc/systemd/system")
    pasta_nginx: Path = Path("/etc/nginx")
    usuario_do_servico: str = "freenfse"
    python: str = "python3.14"
    frontend_pronto: Path | None = None
    espera_da_saude: int = 240
    extras: dict = field(default_factory=dict)

    @property
    def https(self):
        """Se o acesso será por HTTPS (Let's Encrypt ou certificado próprio)."""
        return self.tls in ("letsencrypt", "proprio")

    @property
    def env(self):
        """Caminho do arquivo `.env` (no Compose, na raiz do repositório; no nativo, em /etc)."""
        if self.arquivo_env:
            return Path(self.arquivo_env)
        if self.modo == "compose":
            return self.repositorio / ".env"
        return Path("/etc/freenfse/freenfse.env")

    @property
    def url(self):
        """Endereço público da instalação."""
        if self.https:
            sufixo = "" if self.porta_https == 443 else f":{self.porta_https}"
            return f"https://{self.dominio}{sufixo}"
        sufixo = "" if self.porta_http == 80 else f":{self.porta_http}"
        return f"http://{self.dominio}{sufixo}"


def _eh_ip(texto):
    try:
        ipaddress.ip_address(texto)
    except ValueError:
        return False
    return True


def validar_dominio(dominio):
    """Aceita nome de host/domínio ou IP; recusa endereço com esquema, caminho ou espaço."""
    dominio = (dominio or "").strip().lower()
    if not dominio:
        raise ErroDeParametro("Informe o domínio (ou IP) pelo qual o sistema será acessado.")
    if _eh_ip(dominio) or _DOMINIO.match(dominio):
        return dominio
    raise ErroDeParametro(
        f"'{dominio}' não parece um domínio válido. Use só o nome (ex.: nfse.suaempresa.com.br), "
        "sem http://, barras ou espaços."
    )


def validar_email(email, *, obrigatorio=False):
    """Valida o formato do e-mail."""
    email = (email or "").strip()
    if not email:
        if obrigatorio:
            raise ErroDeParametro("Informe o e-mail para o certificado TLS (--email).")
        return ""
    if not _EMAIL.match(email):
        raise ErroDeParametro(f"'{email}' não parece um e-mail válido.")
    return email


def validar_porta(valor, nome):
    """Porta TCP entre 1 e 65535."""
    try:
        porta = int(valor)
    except (TypeError, ValueError):
        raise ErroDeParametro(f"A porta {nome} precisa ser um número.") from None
    if not 1 <= porta <= 65535:
        raise ErroDeParametro(f"A porta {nome} precisa estar entre 1 e 65535.")
    return porta


def validar(p, *, verificar_arquivos=True):
    """Confere o conjunto de parâmetros; levanta `ErroDeParametro` com a correção sugerida."""
    if p.modo not in ("compose", "nativo"):
        raise ErroDeParametro("O modo precisa ser 'compose' ou 'nativo'.")
    p.dominio = validar_dominio(p.dominio)
    p.porta_http = validar_porta(p.porta_http, "HTTP")
    p.porta_https = validar_porta(p.porta_https, "HTTPS")
    if not Path(p.dados).is_absolute():
        raise ErroDeParametro("O caminho dos dados (--dados) precisa ser absoluto.")
    if p.tls not in ("nenhum", "letsencrypt", "proprio"):
        raise ErroDeParametro("--tls precisa ser nenhum, letsencrypt ou proprio.")
    p.email = validar_email(p.email, obrigatorio=p.tls == "letsencrypt")
    if p.tls == "letsencrypt":
        if _eh_ip(p.dominio) or "." not in p.dominio or p.dominio.endswith(SUFIXOS_NAO_PUBLICOS):
            raise ErroDeParametro(
                "O Let's Encrypt só emite certificado para um domínio público (ex.: "
                "nfse.suaempresa.com.br) que aponte para este servidor. Para um servidor interno, "
                "use --tls proprio com um certificado da sua autoridade."
            )
        if p.porta_http != 80:
            raise ErroDeParametro(
                "O Let's Encrypt valida o domínio pela porta 80 deste servidor: use --porta 80."
            )
    if p.tls == "proprio":
        if not (p.certificado and p.chave_privada):
            raise ErroDeParametro("Com --tls proprio informe --certificado e --chave-privada.")
        if verificar_arquivos:
            for arquivo in (p.certificado, p.chave_privada):
                if not Path(arquivo).is_file():
                    raise ErroDeParametro(f"Arquivo não encontrado: {arquivo}")
    if p.chave_publica_backup and not _CHAVE_PUBLICA_AGE.match(p.chave_publica_backup):
        raise ErroDeParametro(
            "A chave de backup precisa ser a chave PÚBLICA age (começa com age1). Nunca informe "
            "a chave privada (AGE-SECRET-KEY) ao instalador."
        )
    if p.chave_publica_backup and p.gerar_chave_backup:
        raise ErroDeParametro("Use --chave-publica-backup OU --gerar-chave-backup, não os dois.")
    p.email_master = validar_email(p.email_master)
    return p


def montar_parser():
    """Parser da linha de comando."""
    parser = argparse.ArgumentParser(
        prog="instalar.py",
        description=(
            "Instala o freenfse por Docker Compose ou de forma nativa (systemd + Nginx + "
            "Gunicorn). Pode ser executado de novo sem perder dados nem trocar as chaves."
        ),
    )
    parser.add_argument("modo", choices=["compose", "nativo"])
    parser.add_argument("--dominio", help="Domínio (ou IP) de acesso ao sistema.")
    parser.add_argument("--email", help="E-mail do responsável pelo certificado TLS.")
    parser.add_argument("--porta", type=int, default=80, dest="porta_http", help="Porta HTTP.")
    parser.add_argument("--porta-https", type=int, default=443, help="Porta HTTPS.")
    parser.add_argument("--dados", type=Path, help="Pasta dos dados (backups, certificados).")
    parser.add_argument(
        "--tls",
        choices=["nenhum", "letsencrypt", "proprio"],
        help="HTTPS: nenhum (só HTTP), letsencrypt (certbot) ou proprio (seu certificado).",
    )
    parser.add_argument("--certificado", type=Path, help="Certificado (PEM) para --tls proprio.")
    parser.add_argument("--chave-privada", type=Path, help="Chave privada (PEM) do certificado.")
    parser.add_argument("--chave-publica-backup", default="", help="Chave PÚBLICA age (age1...).")
    parser.add_argument(
        "--gerar-chave-backup",
        type=Path,
        help="Gera o par age e grava a chave PRIVADA neste arquivo (leve-o para fora do servidor).",
    )
    parser.add_argument("--email-master", help="Cria o primeiro Master (senha em arquivo 0600).")
    parser.add_argument(
        "--usuario-bi",
        action="store_true",
        dest="criar_usuario_bi",
        help="Cria o usuário de banco somente leitura para BI.",
    )
    parser.add_argument("--nao-interativo", action="store_true", help="Nunca pergunta nada.")
    parser.add_argument(
        "--simular", action="store_true", help="Mostra o plano; não executa nem grava nada."
    )
    parser.add_argument("--arquivo-env", type=Path, help="Onde gravar o .env.")
    parser.add_argument("--python", default="python3.14", help="Python 3.14 (modo nativo).")
    parser.add_argument("--frontend-pronto", type=Path, help="Pasta dist do frontend (nativo).")
    return parser


def perguntar(pergunta, *, padrao="", validador=None, entrada=input):
    """Pergunta no terminal até receber um valor válido (Enter aceita o padrão)."""
    while True:
        sufixo = f" [{padrao}]" if padrao else ""
        resposta = (entrada(f"{pergunta}{sufixo}: ") or "").strip() or padrao
        try:
            return validador(resposta) if validador else resposta
        except ErroDeParametro as erro:
            print(f"  {erro}")


def ler_argumentos(argv, *, entrada=input):
    """Converta `argv` em `Parametros`, perguntando o que faltar (salvo com --nao-interativo)."""
    args = montar_parser().parse_args(argv)
    interativo = not args.nao_interativo
    p = Parametros(
        modo=args.modo,
        dominio=args.dominio or "",
        email=args.email or "",
        porta_http=args.porta_http,
        porta_https=args.porta_https,
        dados=args.dados or Path("/var/lib/freenfse"),
        tls=args.tls or "",
        certificado=args.certificado,
        chave_privada=args.chave_privada,
        chave_publica_backup=args.chave_publica_backup,
        gerar_chave_backup=args.gerar_chave_backup,
        email_master=args.email_master or "",
        criar_usuario_bi=args.criar_usuario_bi,
        simular=args.simular,
        nao_interativo=args.nao_interativo,
        arquivo_env=args.arquivo_env,
        python=args.python,
        frontend_pronto=args.frontend_pronto,
        extras={"dados_explicito": bool(args.dados)},
    )
    if interativo:
        if not p.dominio:
            p.dominio = perguntar(
                "Domínio (ou IP) de acesso ao sistema", validador=validar_dominio, entrada=entrada
            )
        if not args.tls:
            resposta = perguntar(
                "HTTPS: nenhum / letsencrypt / proprio", padrao="nenhum", entrada=entrada
            )
            p.tls = resposta
        if p.tls == "letsencrypt" and not p.email:
            p.email = perguntar(
                "E-mail para o certificado TLS",
                validador=lambda v: validar_email(v, obrigatorio=True),
                entrada=entrada,
            )
        if not args.dados:
            p.dados = Path(perguntar("Pasta dos dados", padrao=str(p.dados), entrada=entrada))
    if not p.tls:
        p.tls = "nenhum"
    return validar(p, verificar_arquivos=not p.simular)
