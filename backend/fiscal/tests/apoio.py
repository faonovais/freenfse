"""Apoio dos testes fiscais: certificados gerados em tempo de teste e transporte HTTP falso.

Nenhum `.pfx` é versionado: cada certificado nasce aqui, com um CNPJ fictício na extensão
ICP-Brasil (OID 2.16.76.1.3.3), e vale só durante o teste.
"""

import datetime as dt
import json
from functools import cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID
from freedfe.excecoes import ComunicacaoErro
from freedfe.transporte import RespostaHttp, TransporteRest

OID_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")
OID_CPF = x509.ObjectIdentifier("2.16.76.1.3.1")
SENHA_DO_PFX = "senha-do-certificado-de-teste-71"


@cache
def _chave_rsa():
    """Uma chave RSA por processo de teste: gerar uma nova a cada certificado seria lento."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _texto_der(texto):
    bruto = texto.encode("ascii")
    return bytes([0x13, len(bruto)]) + bruto  # PrintableString


def gerar_pfx(
    cnpj,
    senha=SENHA_DO_PFX,
    *,
    valido_de=None,
    valido_ate=None,
    cpf=None,
    nome="EMPRESA DE TESTE LTDA",
):
    """Gera um `.pfx` A1 fictício. `cnpj=None` simula um certificado de pessoa física (e-CPF)."""
    agora = dt.datetime.now(dt.UTC)
    valido_de = valido_de or agora - dt.timedelta(days=1)
    valido_ate = valido_ate or agora + dt.timedelta(days=365)
    chave = _chave_rsa()
    sujeito = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, f"{nome}:{cnpj or cpf or 'SEM-DOCUMENTO'}"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ICP-Brasil (teste)"),
        ]
    )
    nomes = []
    if cnpj:
        nomes.append(x509.OtherName(OID_CNPJ, _texto_der(cnpj)))
    if cpf:
        nomes.append(x509.OtherName(OID_CPF, _texto_der("01011990" + cpf + "00000000000")))
    construtor = (
        x509.CertificateBuilder()
        .subject_name(sujeito)
        .issuer_name(sujeito)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valido_de)
        .not_valid_after(valido_ate)
    )
    if nomes:
        construtor = construtor.add_extension(x509.SubjectAlternativeName(nomes), critical=False)
    certificado = construtor.sign(chave, hashes.SHA256())
    return pkcs12.serialize_key_and_certificates(
        b"teste", chave, certificado, None, BestAvailableEncryption(senha.encode())
    )


class TransporteFalso(TransporteRest):
    """Responde às consultas de parâmetros sem rede; guarda o que foi pedido.

    `rotas` mapeia o fim da URL para `(status, corpo)` ou para uma exceção a levantar.
    """

    def __init__(self, rotas):
        self.rotas = rotas
        self.chamadas = []

    def requisitar(self, metodo, url, corpo=None, cabecalhos=None, timeout=None):
        self.chamadas.append((metodo, url))
        for fim, resposta in self.rotas.items():
            if url.endswith(fim):
                if isinstance(resposta, Exception):
                    raise resposta
                status, dados = resposta
                return RespostaHttp(status=status, corpo=json.dumps(dados).encode())
        return RespostaHttp(status=404, corpo=b'{"erros": [{"codigo": "E9999"}]}')


def convenio_aderente(**extra):
    """Resposta de convênio de município aderente (formato observado na produção restrita)."""
    return (
        200,
        {"parametrosConvenio": {"aderenteAmbienteNacional": 1, "aderenteEmissorNacional": 1,
                                "dataAtivacao": "2024-05-02", **extra}},
    )  # fmt: skip


def convenio_nao_aderente():
    """Resposta de convênio de município que não aderiu."""
    return 200, {"parametrosConvenio": {"aderenteAmbienteNacional": 0}}


def falha_de_rede():
    """Falha de transporte (DNS, TLS, timeout)."""
    return ComunicacaoErro("falha de rede simulada")
