"""Único ponto de contato do freenfse com as **operações** da biblioteca fiscal `freedfe`.

A biblioteca só é importada em três lugares: aqui (montar a DPS, emitir, reconciliar, cancelar,
gerar o DANFSe), em `fiscal/persistencia/` (que implementa os contratos de persistência dela) e
em `fiscal/services/certificado.py` (que lê o certificado). Um teste confere essa fronteira. Assim
a biblioteca pode mudar sem espalhar o impacto, e os testes trocam só o transporte HTTP: a Sefin
vira um objeto em memória e nenhum pacote sai para a rede.

O gateway não decide regra de negócio nem mexe em `Nfse`: traduz dados simples (dicionários
e datas) para o modelo da biblioteca, chama a operação e devolve resultados simples. Quem
interpreta o resultado (e grava a situação da nota) é `fiscal/services/emissao.py`.

Segredos: o certificado chega aqui já aberto em memória (`CertificadoA1`) e nunca é gravado.
"""

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal

from freedfe.certificado import CertificadoA1
from freedfe.distribuicao.estado import relogio_utc
from freedfe.excecoes import (
    CertificadoErro,
    ComunicacaoErro,
    EmissaoIncertaErro,
    FreeDFeErro,
    RejeicaoNfseErro,
    RespostaInvalidaErro,
    SincronizacaoEmAndamentoErro,
    ValidacaoErro,
)
from freedfe.interessado import Interessado
from freedfe.nfse.eventos import MotivoCancelamento
from freedfe.nfse.fabrica import criar_servico_nfse
from freedfe.nfse.leiaute import VersaoLeiaute
from freedfe.nfse.modelo import (
    Dps,
    Endereco,
    IbsCbs,
    OpcaoSimplesNacional,
    Prestador,
    RetencaoIssqn,
    Servico,
    Substituicao,
    Tomador,
    TotTrib,
    TribFederal,
    TribMunicipal,
    TributacaoIssqn,
    Valores,
)
from freedfe.nfse.parametros import CacheParametros
from freedfe.nfse.servico import ConfiguracaoNfseLocal
from freedfe.tipos import FUSO_BRASILIA, Ambiente

from fiscal.persistencia.fabrica import Persistencia

logger = logging.getLogger(__name__)

# Esperas entre novas tentativas de uma consulta (a requisição do usuário fica aguardando).
ESPERAS_DA_CONSULTA = (1.0, 2.0)

# Reexporta o que as camadas de cima precisam, sem que elas importem a biblioteca.
TravaOcupadaErro = SincronizacaoEmAndamentoErro

SIMPLES_ME_EPP = 3
MOTIVOS_DE_CANCELAMENTO = {
    1: "Erro na emissão",
    2: "Serviço não prestado",
    9: "Outros",
}


class ErroDeConsultaFiscal(Exception):
    """Falha ao consultar o ambiente nacional; a mensagem está pronta para o usuário."""


class DadosInvalidosErro(Exception):
    """A DPS não pôde ser montada ou foi recusada antes do envio; a mensagem é didática."""


class OperacaoIncertaErro(Exception):
    """Não foi possível confirmar o resultado de uma operação (por exemplo, o cancelamento)."""


class RejeicaoDeEventoErro(Exception):
    """A Sefin recusou um evento (cancelamento); traz os erros no formato do sistema."""

    def __init__(self, erros):
        """Guarda os erros (`codigo`, `descricao`, `complemento`) recusados pela Sefin."""
        super().__init__("; ".join(e["codigo"] for e in erros))
        self.erros = erros


@dataclass
class ContextoFiscal:
    """O que uma operação fiscal precisa: empresa, certificado em memória e persistência.

    `transporte`, `pausa` e `relogio` existem para os testes (Sefin simulada, sem dormir e
    com data controlada); em produção ficam com os valores da biblioteca.
    """

    cnpj: str
    ambiente_producao: bool
    certificado: CertificadoA1
    persistencia: Persistencia
    transporte: object | None = None
    pausa: Callable | None = None
    relogio: Callable = relogio_utc


@dataclass
class ResultadoEmissao:
    """Desfecho de uma tentativa de emissão ou reconciliação, em termos do sistema."""

    estado: str  # ver ESTADO_*
    id_dps: str | None = None
    serie: int | None = None
    numero: int | None = None
    chave: str | None = None
    xml_nfse: bytes | None = None
    xml_dps: bytes | None = None
    leiaute: str = ""
    erros: list = field(default_factory=list)
    mensagem: str = ""
    nao_localizada: bool = False


ESTADO_AUTORIZADA = "autorizada"
ESTADO_REJEITADA = "rejeitada"
ESTADO_INCERTA = "incerta"
ESTADO_NAO_ENVIADA = "nao_enviada"  # recusada localmente: a Sefin nunca viu esta DPS
ESTADO_DESCONHECIDO = "desconhecido"  # falha no meio; o chamador decide pelo estado gravado


def abrir_certificado(arquivo_pfx, senha):
    """Abre o `.pfx` em memória. Levanta `ErroDeConsultaFiscal` se a senha ou o arquivo falham."""
    try:
        return CertificadoA1(arquivo_pfx, senha)
    except CertificadoErro:
        raise ErroDeConsultaFiscal(
            "Não foi possível abrir o certificado digital. Envie-o novamente em Certificado A1."
        ) from None


def _criar_servico(contexto):
    return criar_servico_nfse(
        ambiente=Ambiente.PRODUCAO if contexto.ambiente_producao else Ambiente.HOMOLOGACAO,
        interessado=Interessado(cnpj=contexto.cnpj),
        certificado=contexto.certificado,
        repositorio=contexto.persistencia.repositorio,
        estado_emissao=contexto.persistencia.estado_emissao,
        travas=contexto.persistencia.travas,
        estado_nsu=contexto.persistencia.estado_nsu,
        cache_parametros=contexto.persistencia.cache_parametros,
        evidencias=contexto.persistencia.evidencias,
        auditoria=contexto.persistencia.auditoria,
        transporte=contexto.transporte,
        relogio=contexto.relogio,
        opcoes=ConfiguracaoNfseLocal(esperas_consulta=ESPERAS_DA_CONSULTA, pausa=contexto.pausa),
        pausa=contexto.pausa,
    )


# -- leiaute -----------------------------------------------------------------------------


def leiaute_em_vigor(ambiente_producao, relogio=relogio_utc):
    """Código do leiaute da DPS em vigor agora, pela regra da biblioteca.

    Produção restrita usa sempre a NT 009. Produção usa a NT 004 até 30/11/2026 e a NT 009
    a partir de 01/12/2026. Vale a data em que a Sefin **recebe** a DPS, não a competência.
    """
    ambiente = Ambiente.PRODUCAO if ambiente_producao else Ambiente.HOMOLOGACAO
    hoje = relogio().astimezone(FUSO_BRASILIA).date()
    return VersaoLeiaute.selecionar(ambiente, hoje).value


def descricao_do_leiaute(codigo):
    """Nome legível do leiaute (`NT 004 v2.0`, `NT 009 v1.01`)."""
    return VersaoLeiaute(codigo).descricao if codigo else ""


# -- DPS ---------------------------------------------------------------------------------


def _decimal(valor):
    return Decimal(str(valor)) if valor not in (None, "") else None


def _endereco(dados):
    if dados.get("pais") or dados.get("codigo_postal") or dados.get("cidade"):
        return Endereco.no_exterior(
            dados["logradouro"],
            dados["numero"],
            dados["bairro"],
            dados["pais"],
            dados["codigo_postal"],
            dados["cidade"],
            dados["estado"],
            complemento=dados.get("complemento") or None,
        )
    if dados.get("codigo_municipio"):
        return Endereco.nacional(
            dados["logradouro"],
            dados["numero"],
            dados["bairro"],
            dados["codigo_municipio"],
            dados["cep"],
            complemento=dados.get("complemento") or None,
        )
    return None


def _tomador(dados):
    documento = dados.get("documento") or ""
    e_estrangeiro = dados.get("tipo") == "estrangeiro"
    emails = dados.get("emails_envio") or []
    return Tomador(
        nome=dados["nome"],
        cnpj=documento if dados.get("tipo") == "pj" else None,
        cpf=documento if dados.get("tipo") == "pf" else None,
        nif=dados.get("nif") or None if e_estrangeiro else None,
        motivo_sem_nif=dados.get("motivo_sem_nif") if e_estrangeiro else None,
        inscricao_municipal=dados.get("inscricao_municipal") or None,
        endereco=_endereco(dados),
        telefone=dados.get("telefone") or None,
        email=emails[0] if emails else None,
    )


def _informa_aliquota(prestador):
    """HIPÓTESE (a confirmar em produção restrita): quem informa a alíquota do ISSQN.

    Não optante: sempre. ME/EPP: só com o ISSQN fora do Simples (apuração 2 ou 3). MEI: nunca.
    """
    opcao = int(prestador["opcao_simples"])
    if opcao == OpcaoSimplesNacional.NAO_OPTANTE:
        return True
    if opcao == OpcaoSimplesNacional.ME_EPP:
        return prestador.get("regime_apuracao_simples") in (2, 3)
    return False


def montar_dps(dados):
    """Monta o `Dps` da biblioteca a partir dos dados simples da nota.

    Levanta `DadosInvalidosErro` (mensagem em português) se a biblioteca recusar algum campo.
    """
    try:
        prestador = dados["prestador"]
        servico = dados["servico"]
        valores = dados["valores"]
        totais = dados["totais"]
        retido = bool(totais.get("iss_retido"))
        aliquota = _decimal(servico.get("aliquota_iss"))
        trib_municipal = TribMunicipal(
            tributacao=TributacaoIssqn.TRIBUTAVEL,
            retencao=RetencaoIssqn.RETIDO_PELO_TOMADOR if retido else RetencaoIssqn.NAO_RETIDO,
            aliquota=aliquota if _informa_aliquota(prestador) else None,
        )
        federal = {
            "retencao_irrf": _decimal(totais.get("retencao_irrf")) or None,
            "retencao_csll": _decimal(totais.get("retencao_csll")) or None,
            "retencao_cp": _decimal(totais.get("retencao_inss")) or None,
        }
        simples = _decimal(dados.get("percentual_total_tributos_simples"))
        ibs = dados.get("ibs_cbs")
        substituicao = dados.get("substituicao")
        return Dps(
            serie=dados["serie"],
            numero=dados.get("numero"),
            data_competencia=dados["competencia"],
            codigo_municipio_emissor=dados["codigo_municipio_emissor"],
            prestador=Prestador(
                cnpj=prestador["cnpj"],
                opcao_simples=prestador["opcao_simples"],
                regime_apuracao_simples=prestador.get("regime_apuracao_simples"),
                regime_especial=prestador.get("regime_especial", 0),
            ),
            tomador=_tomador(dados["tomador"]),
            servico=Servico(
                codigo_tributacao_nacional=servico["codigo_tributacao_nacional"],
                descricao=servico["descricao"],
                codigo_municipio_prestacao=dados["codigo_municipio_emissor"],
                codigo_tributacao_municipal=servico.get("codigo_tributacao_municipal") or None,
                codigo_nbs=servico.get("nbs") or None,
                informacoes_complementares=dados.get("informacoes_complementares") or None,
            ),
            valores=Valores(
                servico=_decimal(valores["servico"]),
                desconto_incondicionado=_decimal(valores.get("desconto_incondicionado")),
                desconto_condicionado=_decimal(valores.get("desconto_condicionado")),
                deducao_percentual=_decimal(valores.get("deducao_percentual")),
                deducao_valor=_decimal(valores.get("deducao_valor")),
            ),
            trib_municipal=trib_municipal,
            trib_federal=TribFederal(**federal) if any(federal.values()) else None,
            tot_trib=(
                TotTrib.simples(simples)
                if simples is not None and int(prestador["opcao_simples"]) == SIMPLES_ME_EPP
                else TotTrib.nao_informado()
            ),
            ibs_cbs=(
                IbsCbs(
                    codigo_indicador_operacao=ibs["codigo_indicador_operacao"],
                    indicador_destinatario=int(ibs["indicador_destinatario"]),
                    cst=servico["cst_ibs_cbs"],
                    codigo_classificacao=servico["c_class_trib"],
                )
                if ibs
                else None
            ),
            substituicao=(
                Substituicao(
                    chave_substituida=substituicao["chave"],
                    codigo_motivo=substituicao["codigo_motivo"],
                    motivo=substituicao.get("motivo") or None,
                )
                if substituicao
                else None
            ),
        )
    except ValidacaoErro as erro:
        raise DadosInvalidosErro(str(erro)) from None


# -- emissão -----------------------------------------------------------------------------


def _erros(excecao):
    return [asdict(e) for e in excecao.erros]


def _ler_xml_dps(contexto, id_dps):
    registro = contexto.persistencia.estado_emissao.obter(id_dps)
    if registro is None or not registro.caminho_dps:
        return None
    return contexto.persistencia.evidencias.ler(registro.caminho_dps)


def emitir(contexto, dados):
    """Emita a DPS: a biblioteca numera (ou reaproveita o número de `dados`), assina e envia.

    O envio é protegido pela trava da empresa e **nunca é repetido** depois de um resultado
    incerto: antes de qualquer novo envio da mesma DPS a biblioteca consulta a Sefin.
    `TravaOcupadaErro` sobe sem tradução: o chamador espera e tenta de novo.
    """
    leiaute = leiaute_em_vigor(contexto.ambiente_producao, contexto.relogio)
    try:
        dps = montar_dps(dados)
        servico = _criar_servico(contexto)
        retorno = servico.emitir(dps, leiaute=VersaoLeiaute(leiaute), verificar_parametros=True)
    except TravaOcupadaErro:
        raise
    except DadosInvalidosErro as erro:
        return ResultadoEmissao(ESTADO_NAO_ENVIADA, leiaute=leiaute, mensagem=str(erro))
    except RejeicaoNfseErro as erro:
        return ResultadoEmissao(
            ESTADO_REJEITADA, id_dps=erro.id_dps, erros=_erros(erro), leiaute=leiaute
        )
    except EmissaoIncertaErro as erro:
        return ResultadoEmissao(
            ESTADO_INCERTA,
            id_dps=erro.id_dps,
            leiaute=leiaute,
            mensagem=str(erro),
            nao_localizada=bool(erro.nao_localizada),
        )
    except ValidacaoErro as erro:
        return ResultadoEmissao(ESTADO_NAO_ENVIADA, leiaute=leiaute, mensagem=str(erro))
    except CertificadoErro:
        return ResultadoEmissao(
            ESTADO_NAO_ENVIADA,
            leiaute=leiaute,
            mensagem="O certificado digital não pôde ser usado. Confira a validade e a senha.",
        )
    except (ComunicacaoErro, RespostaInvalidaErro, FreeDFeErro) as erro:
        logger.warning("Emissão interrompida sem desfecho claro: %s", erro)
        return ResultadoEmissao(ESTADO_DESCONHECIDO, leiaute=leiaute, mensagem=str(erro))
    return _autorizada(contexto, retorno, leiaute)


def _autorizada(contexto, retorno, leiaute):
    registro = (
        contexto.persistencia.estado_emissao.obter(retorno.id_dps) if retorno.id_dps else None
    )
    return ResultadoEmissao(
        ESTADO_AUTORIZADA,
        id_dps=retorno.id_dps,
        serie=registro.serie if registro else None,
        numero=registro.numero if registro else None,
        chave=retorno.chave,
        xml_nfse=retorno.xml_nfse,
        xml_dps=_ler_xml_dps(contexto, retorno.id_dps) if retorno.id_dps else None,
        leiaute=leiaute,
    )


def reconciliar(contexto, id_dps, *, descartar_nao_localizada=False):
    """Pergunta à Sefin o que aconteceu com uma DPS de resultado desconhecido. Nunca reenvia.

    Devolve `autorizada` se a nota existe, `incerta` com `nao_localizada` se a Sefin não a
    conhece e `desconhecido` se a consulta também falhou.
    """
    leiaute = leiaute_em_vigor(contexto.ambiente_producao, contexto.relogio)
    try:
        retorno = _criar_servico(contexto).reconciliar(
            id_dps, descartar_nao_localizada=descartar_nao_localizada
        )
    except TravaOcupadaErro:
        raise
    except (ComunicacaoErro, RespostaInvalidaErro, FreeDFeErro) as erro:
        return ResultadoEmissao(
            ESTADO_DESCONHECIDO, id_dps=id_dps, leiaute=leiaute, mensagem=str(erro)
        )
    if retorno is None:
        return ResultadoEmissao(ESTADO_INCERTA, id_dps=id_dps, leiaute=leiaute, nao_localizada=True)
    return _autorizada(contexto, retorno, leiaute)


def xml_da_dps(contexto, id_dps):
    """XML da DPS assinada, exatamente como foi enviado (evidência gravada antes do envio)."""
    return _ler_xml_dps(contexto, id_dps)


# -- consulta, eventos e DANFSe ----------------------------------------------------------


def consultar_nota(contexto, chave):
    """Busca a NFS-e na Sefin pela chave e a guarda; devolve o XML original."""
    try:
        return _criar_servico(contexto).consultar_chave(chave).xml_nfse
    except RejeicaoNfseErro as erro:
        raise RejeicaoDeEventoErro(_erros(erro)) from None
    except (ComunicacaoErro, RespostaInvalidaErro) as erro:
        raise ErroDeConsultaFiscal(
            "Não foi possível falar com a Sefin agora. Tente novamente em alguns minutos."
        ) from erro


def listar_eventos(contexto, chave):
    """Eventos da nota na Sefin (guardados também no repositório local)."""
    try:
        eventos = _criar_servico(contexto).listar_eventos(chave)
    except RejeicaoNfseErro as erro:
        raise RejeicaoDeEventoErro(_erros(erro)) from None
    except (ComunicacaoErro, RespostaInvalidaErro) as erro:
        raise ErroDeConsultaFiscal(
            "Não foi possível consultar os eventos na Sefin agora. Tente novamente."
        ) from erro
    return [
        {
            "tipo_evento": evento.tipo_evento,
            "descricao": evento.descricao or "",
            "data_evento": evento.data_evento,
            "identificador": evento.protocolo or "",
        }
        for evento in eventos
    ]


def cancelar(contexto, chave, codigo_motivo, justificativa):
    """Pede o cancelamento (evento 101101). Só retorna se a Sefin confirmou.

    Levanta `RejeicaoDeEventoErro` se a Sefin recusou (prazo, regra do município…),
    `OperacaoIncertaErro` se a resposta se perdeu e o evento não foi encontrado depois,
    `DadosInvalidosErro` se a justificativa ou o motivo não servem, e `TravaOcupadaErro` se há
    outra operação fiscal em andamento.
    """
    try:
        _criar_servico(contexto).cancelar(
            chave, MotivoCancelamento(int(codigo_motivo)), justificativa
        )
    except TravaOcupadaErro:
        raise
    except ValidacaoErro as erro:
        raise DadosInvalidosErro(str(erro)) from None
    except RejeicaoNfseErro as erro:
        raise RejeicaoDeEventoErro(_erros(erro)) from None
    except (ComunicacaoErro, RespostaInvalidaErro) as erro:
        raise OperacaoIncertaErro(str(erro)) from None


def gerar_danfse(contexto, chave):
    """PDF do DANFSe (com QR Code e marca d'água se cancelada/substituída), em memória."""
    try:
        return _criar_servico(contexto).danfse_bytes(chave)
    except ValidacaoErro as erro:
        raise DadosInvalidosErro(str(erro)) from None


# -- convênio (Fase 2) -------------------------------------------------------------------


class _SemCache(CacheParametros):
    """Não guarda parâmetros: a verificação de convênio sempre consulta o ambiente nacional.

    Com o cache de verdade, uma queda de rede devolveria o valor antigo e a tela mostraria
    "convênio verificado" sem que a verificação tivesse acontecido.
    """

    def _ler(self, municipio, nome):
        return None

    def _gravar(self, municipio, nome, momento, dados):
        return None


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


def verificar_convenio(
    *, cnpj, codigo_municipio, ambiente_producao, certificado, transporte=None, pausa=None
):
    """Consulta o convênio do município e os parâmetros do contribuinte no ambiente nacional.

    Os testes passam um `transporte` falso (e `pausa` vazia): nada sai para a rede.
    """
    from fiscal.persistencia.fabrica import criar_persistencia

    contexto = ContextoFiscal(
        cnpj=cnpj,
        ambiente_producao=ambiente_producao,
        certificado=certificado,
        persistencia=replace(criar_persistencia(interessado=cnpj), cache_parametros=_SemCache()),
        transporte=transporte,
        pausa=pausa,
    )
    try:
        servico = _criar_servico(contexto)
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
