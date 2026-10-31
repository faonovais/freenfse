"""Único ponto de contato do freenfse com a biblioteca fiscal `freedfe`.

Nada fora deste módulo (e de `fiscal/services/certificado.py`, que lê o certificado) importa
`freedfe`. Assim, a biblioteca pode mudar sem espalhar o impacto, e os testes substituem só o
transporte HTTP, sem rede.

Na Fase 2 o gateway serve às consultas de parâmetros municipais (convênio e contribuinte).
A persistência da emissão (numeração, travas, evidências, repositório de XML) chega na
Fase 3; até lá, os contratos de persistência que `criar_servico_nfse` exige são preenchidos
com peças que recusam o uso (`NaoDisponivelNaFase2`), para que ninguém emita por engano.
"""

import logging
from dataclasses import dataclass, field

from freedfe.auditoria import Auditoria
from freedfe.certificado import CertificadoA1
from freedfe.excecoes import (
    CertificadoErro,
    ComunicacaoErro,
    FreeDFeErro,
    RejeicaoNfseErro,
    RespostaInvalidaErro,
    ValidacaoErro,
)
from freedfe.interessado import Interessado
from freedfe.nfse.fabrica import criar_servico_nfse
from freedfe.nfse.parametros import CacheParametros
from freedfe.nfse.servico import ConfiguracaoNfseLocal
from freedfe.tipos import Ambiente

logger = logging.getLogger(__name__)

# Esperas entre novas tentativas de uma consulta (a requisição do usuário fica aguardando).
ESPERAS_DA_CONSULTA = (1.0, 2.0)


class ErroDeConsultaFiscal(Exception):
    """Falha ao consultar o ambiente nacional; a mensagem está pronta para o usuário."""


class NaoDisponivelNaFase2(NotImplementedError):
    """Parte da emissão que só existe a partir da Fase 3."""


class _Indisponivel:
    """Recusa qualquer uso: a emissão não está habilitada na Fase 2."""

    def __getattr__(self, nome):
        raise NaoDisponivelNaFase2("A emissão de NFS-e chega na Fase 3.")


def _fabrica_indisponivel(_recurso):
    raise NaoDisponivelNaFase2("A emissão de NFS-e chega na Fase 3.")


class _SemCache(CacheParametros):
    """Não guarda parâmetros: a verificação de convênio sempre consulta o ambiente nacional."""

    def _ler(self, municipio, nome):
        return None

    def _gravar(self, municipio, nome, momento, dados):
        return None


class _AuditoriaEmLog(Auditoria):
    """Registra as chamadas no log da aplicação. A biblioteca nunca envia XML a esta trilha."""

    def registrar(self, **dados):
        logger.info("freedfe: %s", {k: v for k, v in dados.items() if k != "erro"})


@dataclass
class ResultadoConvenio:
    """Resultado da verificação do convênio do município, em linguagem simples."""

    codigo_municipio: str
    aderente: bool | None
    aderente_emissor_nacional: bool | None
    data_ativacao: str | None
    mensagem: str
    avisos: list[str] = field(default_factory=list)
    contribuinte: dict = field(default_factory=dict)

    def para_dict(self):
        """Forma gravada no banco (JSON)."""
        return {
            "aderente": self.aderente,
            "aderente_emissor_nacional": self.aderente_emissor_nacional,
            "data_ativacao": self.data_ativacao,
            "mensagem": self.mensagem,
            "avisos": self.avisos,
            "contribuinte": self.contribuinte,
        }


def abrir_certificado(arquivo_pfx, senha):
    """Abre o `.pfx` em memória. Levanta `ErroDeConsultaFiscal` se a senha ou o arquivo falham."""
    try:
        return CertificadoA1(arquivo_pfx, senha)
    except CertificadoErro:
        raise ErroDeConsultaFiscal(
            "Não foi possível abrir o certificado digital. Envie-o novamente em Certificado A1."
        ) from None


def _criar_servico(*, cnpj, ambiente_producao, certificado, transporte=None, pausa=None):
    return criar_servico_nfse(
        ambiente=Ambiente.PRODUCAO if ambiente_producao else Ambiente.HOMOLOGACAO,
        interessado=Interessado(cnpj=cnpj),
        certificado=certificado,
        repositorio=_Indisponivel(),
        estado_emissao=_Indisponivel(),
        travas=_fabrica_indisponivel,
        estado_nsu=_fabrica_indisponivel,
        cache_parametros=_SemCache(),
        evidencias=_Indisponivel(),
        auditoria=_AuditoriaEmLog(),
        transporte=transporte,
        opcoes=ConfiguracaoNfseLocal(esperas_consulta=ESPERAS_DA_CONSULTA, pausa=pausa),
        pausa=pausa,
    )


def verificar_convenio(
    *, cnpj, codigo_municipio, ambiente_producao, certificado, transporte=None, pausa=None
):
    """Consulta o convênio do município e os parâmetros do contribuinte no ambiente nacional.

    Os testes passam um `transporte` falso (e `pausa` vazia): nada sai para a rede.
    """
    try:
        servico = _criar_servico(
            cnpj=cnpj,
            ambiente_producao=ambiente_producao,
            certificado=certificado,
            transporte=transporte,
            pausa=pausa,
        )
        convenio = servico.convenio(codigo_municipio, atualizar=True)
    except ComunicacaoErro:
        raise ErroDeConsultaFiscal(
            "Não foi possível falar com o ambiente nacional da NFS-e agora (sem internet ou "
            "serviço fora do ar). Tente novamente em alguns minutos."
        ) from None
    except CertificadoErro:
        raise ErroDeConsultaFiscal(
            "O certificado digital não pôde ser usado na conexão. Confira a validade em "
            "Certificado A1 e envie-o novamente se preciso."
        ) from None
    except RejeicaoNfseErro as erro:
        raise ErroDeConsultaFiscal(
            "O ambiente nacional recusou a consulta: "
            + ("; ".join(str(e) for e in erro.erros) or "sem detalhe")
            + "."
        ) from None
    except RespostaInvalidaErro:
        raise ErroDeConsultaFiscal(
            "O ambiente nacional respondeu de um jeito inesperado. Tente novamente mais tarde."
        ) from None
    except (ValidacaoErro, FreeDFeErro) as erro:
        raise ErroDeConsultaFiscal(f"Não foi possível consultar o convênio: {erro}") from None

    contribuinte, avisos = _consultar_contribuinte(servico, codigo_municipio)
    return ResultadoConvenio(
        codigo_municipio=codigo_municipio,
        aderente=convenio.aderente,
        aderente_emissor_nacional=convenio.aderente_emissor_nacional,
        data_ativacao=convenio.data_ativacao.isoformat() if convenio.data_ativacao else None,
        mensagem="",  # redigida pelo serviço, que conhece o nome do município
        avisos=avisos,
        contribuinte=contribuinte,
    )


def _consultar_contribuinte(servico, codigo_municipio):
    """Retenções e benefícios do contribuinte. A falha aqui não impede o resultado do convênio."""
    try:
        return servico.parametros_contribuinte(codigo_municipio, atualizar=True), []
    except FreeDFeErro:
        return {}, [
            "Não foi possível obter as retenções e benefícios do contribuinte agora; "
            "o convênio foi verificado mesmo assim."
        ]
