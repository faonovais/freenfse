"""Logs estruturados (uma linha JSON por evento) sem segredos nem dados pessoais desnecessários.

Dois mecanismos, ambos obrigatórios no `LOGGING` da aplicação:

* `FormatadorJson` escreve cada evento como JSON de uma linha (`ts`, `nivel`, `logger`,
  `mensagem`, `excecao`): as quebras de linha são escapadas, então um texto vindo de fora não
  forja linhas de log;
* `redigir` (usado pelo formatador e pelo `FiltroDeSegredos`) mascara, na mensagem **e** no texto
  da exceção: os valores reais dos segredos da instalação (SECRET_KEY, senhas, chaves), pares
  `senha=...`/`token: ...`, cabeçalhos `Bearer`, URLs com senha, chaves privadas, CPF e e-mails.

Nenhuma chamada de log do código precisa lembrar de mascarar: a máscara é a última etapa.
"""

import datetime as dt
import json
import logging
import os
import re

from django.conf import settings

MASCARA = "***"
TAMANHO_MINIMO_DO_SEGREDO = 6
_NOMES_SECRETOS = ("SENHA", "PASSWORD", "SECRET", "TOKEN", "CHAVES", "API_KEY", "APIKEY")

_PADROES = [
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "[chave-privada-removida]",
    ),
    (re.compile(r"AGE-SECRET-KEY-[A-Z0-9]+"), "[chave-age-removida]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), rf"\1 {MASCARA}"),
    # URL com usuário e senha (postgres://usuario:senha@host, redis://:senha@host).
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^/\s:@]*):[^@\s/]+@"), rf"\1:{MASCARA}@"),
    # Pares nome=valor / "nome": "valor" cujo nome indica segredo.
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|senha|secret|token|api[_-]?key|authorization"
            r"|private_key|client_secret|pgpassword|segredo)(\"?\s*[:=]\s*\"?)([^\s\",;&}]+)"
        ),
        rf"\1\2{MASCARA}",
    ),
    # CPF (com ou sem pontuação): dado pessoal que não precisa estar no log.
    (re.compile(r"(?<![\d.])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d-])"), "[cpf]"),
    (
        re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})"),
        rf"{MASCARA}@\1",
    ),
]


def _segredos_da_instalacao():
    """Valores reais dos segredos desta instalação (para mascarar onde quer que apareçam)."""
    valores = set()
    candidatos = [getattr(settings, "SECRET_KEY", "")]
    for banco in getattr(settings, "DATABASES", {}).values():
        candidatos.append(banco.get("PASSWORD", ""))
    for item in getattr(settings, "FREENFSE_CHAVES", None) or ():
        candidatos.extend([item, str(item).partition(":")[2]])
    for nome, valor in os.environ.items():
        if any(marca in nome.upper() for marca in _NOMES_SECRETOS):
            candidatos.append(valor)
            if "," in valor:  # FREENFSE_CHAVES=1:abc,2:def
                candidatos.extend(p.partition(":")[2] for p in valor.split(","))
    for valor in candidatos:
        if isinstance(valor, str) and len(valor) >= TAMANHO_MINIMO_DO_SEGREDO:
            valores.add(valor)
    return sorted(valores, key=len, reverse=True)  # os maiores primeiro


def redigir(texto):
    """Devolve `texto` sem segredos nem dados pessoais óbvios (CPF, e-mail)."""
    if not texto:
        return texto
    texto = str(texto)
    for segredo in _segredos_da_instalacao():
        texto = texto.replace(segredo, MASCARA)
    for padrao, troca in _PADROES:
        texto = padrao.sub(troca, texto)
    return texto


class FiltroDeSegredos(logging.Filter):
    """Mascara a mensagem e a exceção do registro, para qualquer formatador."""

    def filter(self, record):
        """Troca a mensagem já formatada e o texto da exceção pelas versões mascaradas."""
        record.msg = redigir(record.getMessage())
        record.args = ()
        if record.exc_info:
            registro_formatador = logging.Formatter()
            record.exc_text = redigir(registro_formatador.formatException(record.exc_info))
        elif record.exc_text:
            record.exc_text = redigir(record.exc_text)
        return True


class FormatadorJson(logging.Formatter):
    """Uma linha JSON por evento, sempre com a mensagem e a exceção mascaradas."""

    def format(self, record):
        """Monta o evento; `redigir` é a última etapa, mesmo sem o filtro configurado."""
        evento = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(
                timespec="milliseconds"
            ),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": redigir(record.getMessage()),
        }
        if record.exc_info:
            evento["excecao"] = redigir(self.formatException(record.exc_info))
        elif record.exc_text:
            evento["excecao"] = redigir(record.exc_text)
        return json.dumps(evento, ensure_ascii=False)
