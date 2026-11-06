"""Município da prestação (issue #29, ADR 0010): `cLocPrestacao` e a incidência do ISSQN.

A decisão do usuário (2026-11-06): o município da prestação é um dado da nota, do modelo e do
rascunho, com o município do emissor como padrão. Vai na DPS como `cLocPrestacao` e, nos serviços
cujo ISSQN é devido no **local da prestação** (aba MUN.INCID_INFO.SERV. do Anexo VI), é o município
cujo convênio a regra da alíquota consulta. Os testes conferem o XML da DPS **assinada** que chega
à Sefin simulada; os do modelo estão em `agendamentos/tests/`.
"""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django_tenants.utils import schema_context
from lxml import etree

from cadastros.models import Servico
from core.permissoes import Perfil
from fiscal.models import Nfse, ParametrosFiscais
from fiscal.services import emissao, local_prestacao
from fiscal.services import nfse as servico_nfse
from fiscal.tests.apoio import criar_cadastros_de_teste, preparar_empresa_para_emitir

pytestmark = pytest.mark.django_db
S = Nfse.Situacao
NS = "{http://www.sped.fazenda.gov.br/nfse}"
NOTAS = "/api/fiscal/notas/"
COMPETENCIA = dt.date(2026, 10, 1)
EMISSOR = "2903201"  # Barreiras/BA: o município do emissor das empresas de teste
SAO_PAULO, PALMAS, BALSAS = "3550308", "1721000", "2101400"
LOCAL_DA_PRESTACAO = "030401"  # Anexo VI: ISSQN devido no local da prestação (LP)
NO_PRESTADOR = "170101"  # Anexo VI: ISSQN devido no estabelecimento do prestador (EP)


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """A tabela de municípios é o que valida o código do município da prestação."""


def _servico_lp():
    """Serviço cujo ISSQN é devido no local da prestação."""
    criar_cadastros_de_teste()
    servico, _ = Servico.objects.get_or_create(
        codigo_tributacao_nacional=LOCAL_DA_PRESTACAO,
        codigo_tributacao_municipal="001",
        defaults={
            "nome": "Serviço prestado fora do estabelecimento",
            "descricao": "Serviço com incidência no local da prestação.",
            "aliquota_iss": Decimal("3.00"),
            "vigencia_inicio": dt.date(2026, 1, 1),
        },
    )
    return servico


def _rascunho(servico=None, **extra):
    tomador, servico_padrao = criar_cadastros_de_teste()
    dados = {
        "tomador": tomador.pk,
        "servico": (servico or servico_padrao).pk,
        "competencia": COMPETENCIA,
        "valores": {"servico": "1000.00"},
        **extra,
    }
    return servico_nfse.criar_rascunho(dados, usuario=None)


def _emitir(empresa, nota):
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    return nota


def _campo(sefin, nome):
    """Texto do campo na última DPS (assinada) recebida pela Sefin; `None` se não foi enviado."""
    achado = next(etree.fromstring(sefin.dps_recebidas[-1]).iter(NS + nome), None)
    return None if achado is None else achado.text


def _convenios_consultados(sefin):
    return {c[1].split("/")[-2] for c in sefin.chamadas if c[1].endswith("/convenio")}


# -- cLocPrestacao na DPS -------------------------------------------------------------------


def test_sem_municipio_da_prestacao_a_dps_leva_o_municipio_do_emissor(empresa_pronta, sefin):
    nota = _emitir(empresa_pronta, _rascunho())

    assert nota.situacao == S.AUTORIZADA
    assert _campo(sefin, "cLocPrestacao") == EMISSOR
    assert nota.complementos["local_prestacao"] == {"codigo": EMISSOR, "origem": "emissor"}


def test_a_dps_leva_o_municipio_da_prestacao_informado_na_nota(empresa_pronta, sefin):
    nota = _emitir(empresa_pronta, _rascunho(codigo_municipio_prestacao=SAO_PAULO))

    assert nota.situacao == S.AUTORIZADA
    assert _campo(sefin, "cLocPrestacao") == SAO_PAULO
    assert nota.complementos["local_prestacao"] == {"codigo": SAO_PAULO, "origem": "nota"}
    assert nota.complementos["municipio_prestacao_nota"] == SAO_PAULO


def test_o_codigo_pode_vir_formatado_e_so_os_digitos_valem(empresa_pronta):
    nota = _rascunho(codigo_municipio_prestacao=" 3550-308 ")

    assert nota.complementos["municipio_prestacao_nota"] == SAO_PAULO


def test_campo_vazio_volta_ao_padrao_do_emissor(empresa_pronta):
    nota = _rascunho(codigo_municipio_prestacao="")

    assert nota.complementos["municipio_prestacao_nota"] is None
    assert nota.complementos["local_prestacao"] == {"codigo": EMISSOR, "origem": "emissor"}


def test_rascunho_antigo_sem_o_campo_continua_usando_o_municipio_do_emissor(empresa_pronta, sefin):
    nota = _rascunho()
    complementos = dict(nota.complementos)
    for chave in ("local_prestacao", "municipio_prestacao_nota", "municipio_prestacao_modelo"):
        complementos.pop(chave)
    Nfse.objects.filter(pk=nota.pk).update(complementos=complementos)
    nota.refresh_from_db()

    nota = _emitir(empresa_pronta, nota)

    assert nota.situacao == S.AUTORIZADA
    assert _campo(sefin, "cLocPrestacao") == EMISSOR


# -- validação ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "trecho"),
    [("9999999", "não encontrado"), ("123", "7 dígitos"), ("35503080", "7 dígitos")],
)
def test_municipio_da_prestacao_inexistente_ou_mal_formado_e_recusado(
    empresa_pronta, codigo, trecho
):
    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        _rascunho(codigo_municipio_prestacao=codigo)

    assert trecho in erro.value.erros["codigo_municipio_prestacao"]


def test_a_correcao_do_rascunho_tambem_valida_o_municipio(empresa_pronta):
    nota = _rascunho()
    tomador, servico = criar_cadastros_de_teste()

    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        servico_nfse.atualizar_rascunho(
            nota,
            {
                "tomador": tomador.pk,
                "servico": servico.pk,
                "competencia": COMPETENCIA,
                "valores": {"servico": "1000.00"},
                "codigo_municipio_prestacao": "9999999",
            },
        )

    assert "codigo_municipio_prestacao" in erro.value.erros


def test_corrigir_o_rascunho_troca_e_remove_o_municipio_da_prestacao(empresa_pronta):
    nota = _rascunho(codigo_municipio_prestacao=SAO_PAULO)
    tomador, servico = criar_cadastros_de_teste()
    base = {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": COMPETENCIA,
        "valores": {"servico": "1000.00"},
    }

    servico_nfse.atualizar_rascunho(nota, {**base, "codigo_municipio_prestacao": PALMAS})
    assert nota.complementos["local_prestacao"] == {"codigo": PALMAS, "origem": "nota"}

    servico_nfse.atualizar_rascunho(nota, {**base, "codigo_municipio_prestacao": ""})
    assert nota.complementos["local_prestacao"] == {"codigo": EMISSOR, "origem": "emissor"}


# -- serviço com incidência no local da prestação (LP) ---------------------------------------


def test_lp_com_prestacao_em_outro_municipio_consulta_o_convenio_da_prestacao(
    empresa_pronta, sefin
):
    """O emissor tem convênio ativo; o da prestação, não: a alíquota passa a ser devida."""
    sefin.municipios_nao_aderentes.add(SAO_PAULO)

    nota = _emitir(empresa_pronta, _rascunho(_servico_lp(), codigo_municipio_prestacao=SAO_PAULO))

    assert nota.situacao == S.AUTORIZADA
    assert _campo(sefin, "cLocPrestacao") == SAO_PAULO
    assert _campo(sefin, "pAliq") == "3.00"
    avaliacao = nota.complementos["aliquota_issqn"]
    assert avaliacao["codigo_regra"] == "E0619" and avaliacao["regra_incidencia"] == "LP"
    assert avaliacao["municipio_incidencia"] == SAO_PAULO
    assert avaliacao["origem_prestacao"] == "nota"
    assert SAO_PAULO in _convenios_consultados(sefin)


def test_lp_com_convenio_ativo_na_prestacao_nao_envia_paliq_mesmo_que_o_do_emissor_nao_esteja(
    empresa_pronta, sefin
):
    """O contrário: o convênio do emissor só ativa depois da competência; o da prestação já estava
    ativo, e é ele que vale para o serviço do local da prestação."""
    parametros = ParametrosFiscais.obter()
    parametros.convenio_resultado = {"aderente": True, "data_ativacao": "2026-10-02"}
    parametros.save()

    nota = _emitir(empresa_pronta, _rascunho(_servico_lp(), codigo_municipio_prestacao=PALMAS))

    assert nota.situacao == S.AUTORIZADA
    assert _campo(sefin, "pAliq") is None
    avaliacao = nota.complementos["aliquota_issqn"]
    assert avaliacao["codigo_regra"] == "E0617"
    assert avaliacao["municipio_incidencia"] == PALMAS


def test_lp_usa_a_data_de_ativacao_do_convenio_da_prestacao(empresa_pronta, sefin):
    """Convênio da prestação ativo só depois da competência (2026-10-01): ainda não vale."""
    sefin.ativacao_do_convenio = {PALMAS: "2026-10-02"}

    nota = _emitir(empresa_pronta, _rascunho(_servico_lp(), codigo_municipio_prestacao=PALMAS))

    assert _campo(sefin, "pAliq") == "3.00"
    assert nota.complementos["aliquota_issqn"]["codigo_regra"] == "E0619"


def test_lp_sem_municipio_informado_usa_o_do_emissor_como_padrao(empresa_pronta, sefin):
    nota = _emitir(empresa_pronta, _rascunho(_servico_lp()))

    assert nota.situacao == S.AUTORIZADA
    assert _campo(sefin, "pAliq") is None  # convênio do emissor ativo: E0617
    avaliacao = nota.complementos["aliquota_issqn"]
    assert avaliacao["municipio_incidencia"] == EMISSOR
    assert avaliacao["origem_prestacao"] == "emissor"
    assert _convenios_consultados(sefin) <= {EMISSOR}


def test_lp_sem_conseguir_consultar_o_convenio_da_prestacao_volta_a_rascunho(empresa_pronta, sefin):
    sefin.fora_do_ar = True
    nota = _rascunho(_servico_lp(), codigo_municipio_prestacao=SAO_PAULO)

    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()

    assert nota.situacao == S.RASCUNHO and sefin.total_de_posts == 0
    assert "convênio ativo" in nota.mensagem


# -- serviço que NÃO é do local da prestação: o campo só consta da nota ----------------------


def test_servico_no_estabelecimento_do_prestador_ignora_o_municipio_da_prestacao(
    empresa_pronta, sefin
):
    sefin.municipios_nao_aderentes.add(SAO_PAULO)

    nota = _emitir(empresa_pronta, _rascunho(codigo_municipio_prestacao=SAO_PAULO))

    assert _campo(sefin, "cLocPrestacao") == SAO_PAULO  # consta da nota
    assert _campo(sefin, "pAliq") is None  # mas o convênio que vale é o do emissor (E0617)
    avaliacao = nota.complementos["aliquota_issqn"]
    assert avaliacao["regra_incidencia"] == "EP"
    assert avaliacao["municipio_incidencia"] == EMISSOR
    assert avaliacao["origem_prestacao"] is None
    assert SAO_PAULO not in _convenios_consultados(sefin)


def test_servico_no_estabelecimento_do_prestador_avisa_que_o_campo_so_consta_da_nota(
    empresa_pronta,
):
    tomador, servico = criar_cadastros_de_teste()

    preparo = servico_nfse.preparar(
        {
            "tomador": tomador.pk,
            "servico": servico.pk,
            "competencia": COMPETENCIA,
            "valores": {"servico": "1000.00"},
            "codigo_municipio_prestacao": SAO_PAULO,
        }
    )

    assert any("município da prestação" in aviso for aviso in preparo.avisos)


def test_servico_do_local_da_prestacao_nao_recebe_o_aviso_porque_o_municipio_vale_para_a_regra(
    empresa_pronta,
):
    tomador, _ = criar_cadastros_de_teste()

    preparo = servico_nfse.preparar(
        {
            "tomador": tomador.pk,
            "servico": _servico_lp().pk,
            "competencia": COMPETENCIA,
            "valores": {"servico": "1000.00"},
            "codigo_municipio_prestacao": SAO_PAULO,
        }
    )

    assert not any("município da prestação" in aviso for aviso in preparo.avisos)


def test_prestacao_no_proprio_emissor_nao_gera_aviso(empresa_pronta):
    tomador, servico = criar_cadastros_de_teste()

    preparo = servico_nfse.preparar(
        {
            "tomador": tomador.pk,
            "servico": servico.pk,
            "competencia": COMPETENCIA,
            "valores": {"servico": "1000.00"},
            "codigo_municipio_prestacao": EMISSOR,
        }
    )

    assert not any("município da prestação" in aviso for aviso in preparo.avisos)


# -- a conferência (prévia) -----------------------------------------------------------------


def test_a_previa_mostra_o_municipio_de_incidencia_e_de_onde_ele_veio(empresa_pronta):
    servico = _servico_lp()
    tomador, _ = criar_cadastros_de_teste()

    preparo = servico_nfse.preparar(
        {
            "tomador": tomador.pk,
            "servico": servico.pk,
            "competencia": COMPETENCIA,
            "valores": {"servico": "1000.00"},
            "codigo_municipio_prestacao": SAO_PAULO,
        }
    )

    decisao = preparo.complementos["aliquota_issqn"]
    assert decisao["municipio_incidencia"] == SAO_PAULO
    assert decisao["regra_incidencia"] == "LP" and decisao["origem_prestacao"] == "nota"
    assert preparo.complementos["local_prestacao"] == {"codigo": SAO_PAULO, "origem": "nota"}


# -- a nota substituta herda o município ----------------------------------------------------


def test_a_nota_substituta_leva_o_mesmo_municipio_da_prestacao(empresa_pronta, sefin):
    original = _emitir(empresa_pronta, _rascunho(codigo_municipio_prestacao=SAO_PAULO))

    substituta = servico_nfse.criar_substituta(
        original, codigo_motivo="99", motivo="Correção de dados da nota original.", usuario=None
    )
    substituta = _emitir(empresa_pronta, substituta)

    assert substituta.situacao == S.AUTORIZADA
    assert _campo(sefin, "cLocPrestacao") == SAO_PAULO


# -- o resolvedor (prioridade nota > modelo > emissor) ---------------------------------------


def _parametros(emissor=EMISSOR):
    return SimpleNamespace(codigo_municipio_emissor=emissor)


def test_prioridade_nota_depois_modelo_depois_emissor():
    assert local_prestacao.resolver(SAO_PAULO, PALMAS, _parametros()) == (SAO_PAULO, "nota")
    assert local_prestacao.resolver(None, PALMAS, _parametros()) == (PALMAS, "modelo")
    assert local_prestacao.resolver("", "", _parametros()) == (EMISSOR, "emissor")
    assert local_prestacao.resolver(None, None, _parametros()) == (EMISSOR, "emissor")


def test_sem_nenhum_municipio_o_resolvedor_nao_inventa_um():
    assert local_prestacao.resolver(None, None, _parametros(emissor="")) == (None, None)


# -- API: entrada, prévia e padrão da empresa ------------------------------------------------


@pytest.fixture
def emissor_da_empresa(api_de, empresa_a):
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
        tomador, servico = criar_cadastros_de_teste()
        servico_lp = _servico_lp()
    corpo = {
        "tomador": tomador.pk,
        "servico": servico_lp.pk,
        "competencia": "2026-10-01",
        "valores": {"servico": "1500.00"},
    }
    return api_de(empresa_a, Perfil.EMISSOR), corpo


def test_prontidao_informa_o_padrao_do_municipio_da_prestacao(emissor_da_empresa):
    api, _ = emissor_da_empresa

    corpo = api.get(f"{NOTAS}prontidao/").json()

    assert corpo["municipio_prestacao_padrao"] == EMISSOR


def test_previa_pela_api_mostra_a_incidencia_no_municipio_da_prestacao(emissor_da_empresa):
    api, corpo = emissor_da_empresa

    resposta = api.post(f"{NOTAS}previa/", {**corpo, "codigo_municipio_prestacao": SAO_PAULO})

    assert resposta.status_code == 200
    complementos = resposta.json()["complementos"]
    assert complementos["local_prestacao"] == {"codigo": SAO_PAULO, "origem": "nota"}
    assert complementos["aliquota_issqn"]["municipio_incidencia"] == SAO_PAULO


def test_previa_recusa_municipio_inexistente_com_a_mensagem_no_campo(emissor_da_empresa):
    api, corpo = emissor_da_empresa

    resposta = api.post(f"{NOTAS}previa/", {**corpo, "codigo_municipio_prestacao": "9999999"})

    assert resposta.status_code == 400
    assert "não encontrado" in resposta.json()["codigo_municipio_prestacao"]


def test_criar_pela_api_grava_o_municipio_e_a_nota_reabre_com_ele(emissor_da_empresa):
    api, corpo = emissor_da_empresa

    criada = api.post(NOTAS, {**corpo, "codigo_municipio_prestacao": PALMAS})

    assert criada.status_code == 201
    assert criada.json()["complementos"]["municipio_prestacao_nota"] == PALMAS
    assert criada.json()["complementos"]["local_prestacao"]["origem"] == "nota"
