"""Geração de segredos e gravação do `.env` (permissão 600, idempotente, sem imprimir segredos)."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import tempfile
from pathlib import Path

# Chaves cujo valor, uma vez gerado, NUNCA é trocado por uma nova execução do instalador:
# trocar SECRET_KEY invalida as sessões; trocar POSTGRES_PASSWORD desconecta o banco; trocar
# FREENFSE_CHAVES tornaria ilegíveis os certificados, as credenciais e os XMLs já gravados.
SEGREDOS = ("SECRET_KEY", "POSTGRES_PASSWORD", "FREENFSE_CHAVES", "FREENFSE_BI_SENHA")
_LINHA = re.compile(r"^\s*(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def gerar_senha(tamanho=32):
    """Senha aleatória (URL-safe)."""
    return secrets.token_urlsafe(tamanho)


def gerar_chave_de_criptografia():
    """Chave AES-256 (32 bytes aleatórios em base64 URL-safe), igual a `manage.py gerar_chave`."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def verificador_scram(senha, *, iteracoes=4096):
    """Verificador SCRAM-SHA-256 para `CREATE ROLE ... PASSWORD`: a senha não vai ao servidor."""
    sal = os.urandom(16)
    derivada = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, iteracoes)
    chave_cliente = hmac.new(derivada, b"Client Key", hashlib.sha256).digest()
    armazenada = hashlib.sha256(chave_cliente).digest()
    servidor = hmac.new(derivada, b"Server Key", hashlib.sha256).digest()
    b64 = base64.b64encode
    return (
        f"SCRAM-SHA-256${iteracoes}:{b64(sal).decode()}"
        f"${b64(armazenada).decode()}:{b64(servidor).decode()}"
    )


def ler_env(caminho):
    """Valores do `.env` existente (vazio se não existe). Ignora comentários."""
    caminho = Path(caminho)
    if not caminho.is_file():
        return {}
    valores = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        correspondencia = _LINHA.match(linha)
        if correspondencia and not correspondencia.group(1):
            valores[correspondencia.group(2)] = correspondencia.group(3).strip()
    return valores


def montar_valores(existente, desejados, *, gerador=None):
    """Combina o que já existe com o que o instalador define.

    Retorna `(valores, gerados)`. Segredos que já têm valor são preservados; os que faltam são
    gerados. Os demais (domínio, portas, TLS…) são os `desejados`, que vencem os antigos.
    """
    gerador = gerador or {
        "SECRET_KEY": lambda: gerar_senha(64),
        "POSTGRES_PASSWORD": lambda: gerar_senha(24),
        "FREENFSE_CHAVES": lambda: f"1:{gerar_chave_de_criptografia()}",
        "FREENFSE_BI_SENHA": lambda: gerar_senha(24),
    }
    valores = dict(desejados)
    gerados = []
    for nome in SEGREDOS:
        if existente.get(nome):
            valores[nome] = existente[nome]  # nunca troca um segredo existente
        elif nome in desejados and desejados[nome]:
            valores[nome] = desejados[nome]
        elif nome in gerador:
            valores[nome] = gerador[nome]()
            gerados.append(nome)
    return valores, gerados


def _atualizar_linhas(linhas, valores):
    """Troca o valor das chaves em `linhas`; devolve as linhas e as chaves que não existiam.

    Se a chave tem uma linha ativa (`CHAVE=...`), é ela que muda (a última, que é a que vale);
    senão, a primeira linha comentada (`# CHAVE=...`, o exemplo do `.env.example`) é ativada.
    """
    saida = list(linhas)
    ausentes = dict(valores)
    for nome, valor in valores.items():
        ativas, comentadas = [], []
        for indice, linha in enumerate(saida):
            correspondencia = _LINHA.match(linha)
            if correspondencia and correspondencia.group(2) == nome:
                (comentadas if correspondencia.group(1) else ativas).append(indice)
        alvo = ativas[-1] if ativas else (comentadas[0] if comentadas else None)
        if alvo is not None:
            saida[alvo] = f"{nome}={valor}"
            ausentes.pop(nome)
    return saida, ausentes


def escrever_env(caminho, valores, *, modelo=None):
    """Grava `caminho` com permissão 600, de forma atômica, atualizando só as chaves dadas.

    Parte do `modelo` (ex.: `.env.example`, com os comentários) quando o arquivo não existe; se
    existe, preserva tudo o que não foi mencionado. Chaves ausentes são acrescentadas no fim.
    """
    caminho = Path(caminho)
    if caminho.is_file():
        texto = caminho.read_text(encoding="utf-8")
    elif modelo is not None and Path(modelo).is_file():
        texto = Path(modelo).read_text(encoding="utf-8")
    else:
        texto = ""
    saida, ausentes = _atualizar_linhas(texto.splitlines(), valores)
    if ausentes:
        saida += ["", "# Acrescentado pelo instalador"]
        saida += [f"{nome}={valor}" for nome, valor in ausentes.items()]
    conteudo = "\n".join(saida).rstrip("\n") + "\n"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    descritor, temporario = tempfile.mkstemp(dir=caminho.parent, prefix=".env-")
    try:
        os.fchmod(descritor, 0o600)
        with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
            arquivo.write(conteudo)
        os.replace(temporario, caminho)
    finally:
        if os.path.exists(temporario):
            os.unlink(temporario)
    os.chmod(caminho, 0o600)


def mascarar(texto, segredos):
    """Troca por `***` qualquer valor secreto que apareça em `texto`."""
    for valor in sorted({s for s in segredos if s and len(s) >= 6}, key=len, reverse=True):
        texto = texto.replace(valor, "***")
    return texto
