"""Leitura e conferência da credencial JSON de conta de serviço do Google (Drive e Gmail).

O JSON inteiro é segredo: fica em campo criptografado e nunca volta em resposta, log ou
auditoria. Aqui só se confere a **forma** (sem rede) e se extrai o e-mail da conta, que não é
segredo e serve para o usuário saber com quem compartilhar a pasta.
"""

import json


class CredencialInvalida(Exception):
    """A credencial não serve; a mensagem explica ao usuário o que enviar."""


CAMPOS_OBRIGATORIOS = ("client_email", "private_key", "token_uri")


def ler_conta_de_servico(texto):
    """Converta o JSON da conta de serviço em dicionário (ou levante `CredencialInvalida`)."""
    try:
        dados = json.loads(texto or "")
    except TypeError, ValueError:
        raise CredencialInvalida(
            "O arquivo não é um JSON válido. Envie o arquivo de chave da conta de serviço, "
            "baixado do Google Cloud."
        ) from None
    if not isinstance(dados, dict) or dados.get("type") != "service_account":
        raise CredencialInvalida(
            "Este JSON não é de uma conta de serviço. No Google Cloud, crie uma chave JSON para "
            "a conta de serviço e envie esse arquivo."
        )
    faltando = [campo for campo in CAMPOS_OBRIGATORIOS if not dados.get(campo)]
    if faltando:
        raise CredencialInvalida(
            f"A chave da conta de serviço está incompleta (faltam: {', '.join(faltando)})."
        )
    return dados
