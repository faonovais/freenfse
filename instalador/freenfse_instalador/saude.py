"""Verificação final: o sistema responde e a saúde (banco, Redis, worker, agendador) está boa."""

import http.client
import json
import ssl
import time


class FalhaNaVerificacao(Exception):
    """O sistema não ficou saudável no prazo."""


def consultar(host, porta, dominio, *, https=False, tempo=10):
    """Uma consulta a `/api/saude/`; devolve `(codigo_http, corpo_json_ou_vazio)`.

    Fala com o próprio servidor (127.0.0.1) usando o domínio no cabeçalho `Host`; com HTTPS não
    valida o certificado (é uma sonda local de prontidão, não uma conexão de usuário).
    """
    if https:
        contexto = ssl._create_unverified_context()  # noqa: S323
        conexao = http.client.HTTPSConnection(host, porta, timeout=tempo, context=contexto)
    else:
        conexao = http.client.HTTPConnection(host, porta, timeout=tempo)
    try:
        conexao.request(
            "GET", "/api/saude/", headers={"Host": dominio, "Accept": "application/json"}
        )
        resposta = conexao.getresponse()
        corpo = resposta.read().decode("utf-8", "replace")
        try:
            dados = json.loads(corpo)
        except ValueError:
            dados = {}
        return resposta.status, dados
    finally:
        conexao.close()


def aguardar(consulta, *, espera_total=240, intervalo=5, dormir=time.sleep, relogio=time.monotonic):
    """Repete `consulta()` até `status` ser `ok` ou `degradado` (HTTP 200) ou o prazo acabar.

    `degradado` é aceito: logo após instalar, o backup ainda não rodou e o agendador ainda não
    bateu; `falha` (banco ou Redis fora) não é. Devolve o corpo da última resposta boa.
    """
    limite = relogio() + espera_total
    ultimo = "sem resposta"
    while True:
        try:
            codigo, corpo = consulta()
            if codigo == 200 and corpo.get("status") in ("ok", "degradado"):
                return corpo
            ultimo = f"HTTP {codigo}, estado {corpo.get('status', 'desconhecido')}"
        except OSError as erro:
            ultimo = f"sem conexão ({type(erro).__name__})"
        if relogio() >= limite:
            raise FalhaNaVerificacao(
                f"O sistema não ficou saudável em {espera_total} s (último resultado: {ultimo}). "
                "Veja os logs: `docker compose logs backend` (Compose) ou "
                "`journalctl -u freenfse-web` (nativo)."
            )
        dormir(intervalo)
