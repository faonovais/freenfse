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
from django.utils import timezone
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
    agora = timezone.now()  # o relógio do Django: acompanha o `agora_fixo` dos testes
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


def preparar_empresa_para_emitir(empresa, *, ambiente="producao_restrita", municipio="2903201"):
    """Deixa a empresa **do schema ativo** pronta para emitir: certificado, parâmetros e convênio.

    Chamar dentro de `schema_context(empresa.schema_name)`. O certificado é gerado na hora, com
    o CNPJ da empresa, e guardado cifrado como no sistema real.
    """
    from fiscal.models import Certificado, ParametrosFiscais

    agora = timezone.now()
    Certificado.objects.all().delete()
    Certificado.objects.create(
        arquivo_pfx=gerar_pfx(empresa.cnpj),
        senha=SENHA_DO_PFX,
        titular="EMPRESA DE TESTE LTDA",
        cnpj_titular=empresa.cnpj,
        valido_de=agora - dt.timedelta(days=1),
        valido_ate=agora + dt.timedelta(days=365),
        impressao_digital="a" * 64,
    )
    parametros = ParametrosFiscais.obter()
    parametros.regime_tributario = ParametrosFiscais.RegimeTributario.OUTRO
    parametros.serie_dps = 900
    parametros.ambiente = ambiente
    parametros.codigo_municipio_emissor = municipio
    parametros.convenio_verificado_em = agora
    parametros.convenio_codigo_municipio = municipio
    parametros.convenio_ambiente = ambiente
    parametros.convenio_resultado = {"aderente": True, "mensagem": "Convênio ativo."}
    parametros.save()
    return parametros


class RelogioControlavel:
    """Relógio UTC que só anda quando o teste manda (`avancar(minutes=5)`)."""

    def __init__(self, inicio=None):
        self.agora = inicio or dt.datetime(2026, 11, 2, 15, 0, tzinfo=dt.UTC)

    def __call__(self):
        return self.agora

    def avancar(self, **intervalo):
        """Avança o relógio."""
        self.agora += dt.timedelta(**intervalo)


def criar_cadastros_de_teste():
    """Tomador (PJ) e serviço vigente de teste, no schema ativo; devolve `(tomador, servico)`."""
    from decimal import Decimal

    from cadastros.models import Pessoa, Servico
    from conftest import CNPJ_C

    tomador, _ = Pessoa.objects.get_or_create(
        documento=CNPJ_C,
        defaults={
            "tipo": Pessoa.Tipo.PESSOA_JURIDICA,
            "nome": "TOMADOR FICTICIO LTDA",
            "logradouro": "Rua das Flores",
            "numero": "100",
            "bairro": "Centro",
            "codigo_municipio": "2903201",
            "cep": "47800000",
            "emails_envio": ["financeiro@tomador.test"],
        },
    )
    servico, _ = Servico.objects.get_or_create(
        codigo_tributacao_nacional="170101",
        codigo_tributacao_municipal="001",
        defaults={
            "nome": "Consultoria",
            "descricao": "Consultoria em gestão agrícola.",
            "aliquota_iss": Decimal("2.00"),
            "vigencia_inicio": dt.date(2026, 1, 1),
        },
    )
    return tomador, servico


def criar_rascunho_de_teste(*, valor="1000.00", competencia=None, usuario=None, **extra):
    """Cria (no schema ativo) um tomador, um serviço vigente e o rascunho da nota."""
    from fiscal.services import nfse as servico_nfse

    tomador, servico = criar_cadastros_de_teste()
    dados = {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": competencia or dt.date(2026, 10, 1),
        "valores": {"servico": valor},
    }
    dados.update(extra)
    return servico_nfse.criar_rascunho(dados, usuario=usuario)
