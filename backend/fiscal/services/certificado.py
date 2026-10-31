"""Certificado A1: validação no envio, guarda cifrada e leitura em memória.

O `.pfx` e a senha só existem em claro na memória, durante a requisição ou a consulta que os
usa; no banco ficam cifrados (campos de `core.fields`) e nenhuma resposta, log ou registro de
auditoria os contém. A validação usa `freedfe.certificado.CertificadoA1`.
"""

import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.serialization import Encoding
from django.utils import timezone
from freedfe.certificado import CertificadoA1
from freedfe.excecoes import CertificadoErro

from core.models import LogAuditoria
from core.services import auditoria
from fiscal.models import AlertaCertificado, Certificado

LIMITE_ARQUIVO_BYTES = 256 * 1024


class ErroDeCertificado(Exception):
    """O certificado foi recusado; a mensagem é exibida ao usuário e não traz segredos."""


@dataclass(frozen=True)
class DadosDoCertificado:
    """Metadados lidos do `.pfx` (nada secreto)."""

    titular: str
    cnpj: str
    valido_de: object
    valido_ate: object
    impressao_digital: str


def _ler(arquivo, senha):
    if not arquivo:
        raise ErroDeCertificado("Escolha o arquivo do certificado (.pfx ou .p12).")
    if len(arquivo) > LIMITE_ARQUIVO_BYTES:
        raise ErroDeCertificado(
            f"O arquivo é grande demais para um certificado A1 (máximo de "
            f"{LIMITE_ARQUIVO_BYTES // 1024} KB)."
        )
    if not senha:
        raise ErroDeCertificado("Informe a senha do certificado.")
    try:
        a1 = CertificadoA1(arquivo, senha)
    except CertificadoErro:
        raise ErroDeCertificado(
            "Não foi possível abrir o certificado. Confira se a senha está correta e se o "
            "arquivo é um certificado A1 (.pfx ou .p12)."
        ) from None
    info = a1.info()
    return a1, info


def validar_para_empresa(empresa, arquivo, senha, *, mesma_raiz=False, agora=None):
    """Valida senha, CNPJ do titular e validade; devolve os metadados do certificado.

    O CNPJ do titular deve ser o da empresa. Com `mesma_raiz`, também vale o de outro
    estabelecimento da mesma empresa (mesmos 8 primeiros caracteres), por escolha explícita.
    """
    agora = agora or timezone.now()
    a1, info = _ler(arquivo, senha)
    if not info.cnpj:
        raise ErroDeCertificado(
            "O certificado não traz CNPJ (parece ser de pessoa física). Envie o certificado A1 "
            "da empresa."
        )
    cnpj_certificado, cnpj_empresa = info.cnpj.upper(), empresa.cnpj.upper()
    if cnpj_certificado != cnpj_empresa:
        if cnpj_certificado[:8] == cnpj_empresa[:8]:
            if not mesma_raiz:
                raise ErroDeCertificado(
                    "O certificado é de outro estabelecimento da mesma empresa (CNPJ "
                    f"{cnpj_certificado}). Se for o certificado da matriz ou de uma filial, "
                    "marque a opção que autoriza usar um certificado da mesma raiz de CNPJ."
                )
        else:
            raise ErroDeCertificado(
                f"O CNPJ do certificado ({cnpj_certificado}) é diferente do CNPJ da empresa "
                f"({cnpj_empresa})."
            )
    if info.valido_de > agora:
        raise ErroDeCertificado(f"O certificado só passa a valer em {info.valido_de:%d/%m/%Y}.")
    if info.valido_ate < agora:
        raise ErroDeCertificado(f"O certificado venceu em {info.valido_ate:%d/%m/%Y}.")
    return DadosDoCertificado(
        titular=info.titular[:500],
        cnpj=cnpj_certificado,
        valido_de=info.valido_de,
        valido_ate=info.valido_ate,
        impressao_digital=hashlib.sha256(
            a1.certificado_x509.public_bytes(Encoding.DER)
        ).hexdigest(),
    )


def enviar_certificado(*, request, empresa, arquivo, senha, mesma_raiz=False):
    """Valida e guarda (cifrado) o certificado da empresa, substituindo o anterior."""
    dados = validar_para_empresa(empresa, arquivo, senha, mesma_raiz=mesma_raiz)
    certificado = Certificado(
        arquivo_pfx=bytes(arquivo),
        senha=senha,
        titular=dados.titular,
        cnpj_titular=dados.cnpj,
        valido_de=dados.valido_de,
        valido_ate=dados.valido_ate,
        impressao_digital=dados.impressao_digital,
        mesma_raiz_autorizada=mesma_raiz and dados.cnpj != empresa.cnpj.upper(),
        enviado_por=getattr(request.user, "email", ""),
    )
    certificado.save()
    auditoria.registrar(
        LogAuditoria.Acao.CERTIFICADO_ENVIADO,
        request=request,
        alvo=f"certificado:{dados.impressao_digital[:16]}",
        detalhes={
            "cnpj_titular": dados.cnpj,
            "valido_ate": dados.valido_ate.isoformat(),
            "mesma_raiz": certificado.mesma_raiz_autorizada,
        },
    )
    return certificado


def remover_certificado(*, request):
    """Apaga o certificado cifrado (e seus alertas); devolve `False` se não havia nenhum."""
    certificado = Certificado.objects.first()
    if certificado is None:
        return False
    impressao = certificado.impressao_digital
    certificado.delete()
    AlertaCertificado.objects.filter(impressao_digital=impressao).delete()
    auditoria.registrar(
        LogAuditoria.Acao.CERTIFICADO_REMOVIDO,
        request=request,
        alvo=f"certificado:{impressao[:16]}",
    )
    return True


def abrir_em_memoria(certificado):
    """Decifra o `.pfx` e a senha e devolve o `CertificadoA1` (somente para o uso imediato)."""
    return CertificadoA1(bytes(certificado.arquivo_pfx), certificado.senha)
