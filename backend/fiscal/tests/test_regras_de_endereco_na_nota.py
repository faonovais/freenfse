"""E0239, E0243, E0919 e E0901 aplicadas à nota: prévia, rascunho, solicitação e execução (#33).

A função pura está em `test_regras_de_endereco.py`. Aqui se confere que o bloqueio chega à tela com
o código da regra, que vale só com o grupo de IBS/CBS, que o rascunho antigo é barrado de novo ao
pedir a emissão e ao enviá-la, e que a DPS assinada só sai quando a regra é atendida.
"""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django_tenants.utils import schema_context

from cadastros.models import Pessoa, Servico
from conftest import cnpj_de_teste, cpf_de_teste
from core.permissoes import Perfil
from fiscal.models import Nfse
from fiscal.referencias import local_fornecimento
from fiscal.services import emissao
from fiscal.services import nfse as servico_nfse
from fiscal.tests.apoio import (
    criar_cadastros_de_teste,
    criar_destinatario_de_teste,
    preparar_empresa_para_emitir,
)

pytestmark = pytest.mark.django_db
S = Nfse.Situacao
HOJE = dt.date(2026, 10, 31)
NOTAS = "/api/fiscal/notas/"
EXIGE, NAO_EXIGE = "000001", "410009"
ADQUIRENTE, DESTINATARIO, OUTRO = "100301", "100302", "030101"
OUTRA_PESSOA = {"indicador_destinatario": 1}
O_PROPRIO_TOMADOR = {"indicador_destinatario": 0}
AVISO_130201 = local_fornecimento.AVISO_DO_TEXTO_DO_ADQUIRENTE


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """A tabela de municípios valida o município do emissor e o dos cadastros."""


def _servico(municipal, **campos):
    base = {
        "nome": f"Serviço {municipal}",
        "descricao": "Análise e desenvolvimento de sistemas.",
        "codigo_tributacao_nacional": "010101",
        "codigo_tributacao_municipal": municipal,
        "nbs": "115021000",
        "aliquota_iss": Decimal("2.00"),
        "vigencia_inicio": dt.date(2026, 1, 1),
    }
    return Servico.objects.create(**{**base, **campos})


@pytest.fixture
def cadastros(empresa_pronta):
    """Tomador PJ completo, serviço que exige o grupo, o que não exige e um destinatário."""
    tomador, _ = criar_cadastros_de_teste()
    exige = _servico(
        "002", cst_ibs_cbs="000", c_class_trib=EXIGE, codigo_indicador_operacao=ADQUIRENTE
    )
    nao_exige = _servico(
        "003", cst_ibs_cbs="410", c_class_trib=NAO_EXIGE, codigo_indicador_operacao=ADQUIRENTE
    )
    return SimpleNamespace(
        tomador=tomador,
        exige=exige,
        nao_exige=nao_exige,
        destinatario=criar_destinatario_de_teste(),
    )


def _tomador_de_fora():
    return Pessoa.objects.create(
        tipo=Pessoa.Tipo.ESTRANGEIRO,
        nif="NIF-998877",
        nome="CLIENTE NO EXTERIOR",
        logradouro="Main Street",
        numero="10",
        bairro="Downtown",
        pais="US",
        codigo_postal="10001",
        cidade="New York",
        estado="NY",
    )


def _tomador_sem_endereco():
    """Como um cadastro antigo: PJ sem endereço (o cadastro de hoje não deixaria gravar)."""
    return Pessoa.objects.create(
        tipo=Pessoa.Tipo.PESSOA_JURIDICA,
        documento=cnpj_de_teste("054239600002"),
        nome="TOMADOR SEM ENDERECO LTDA",
    )


def _dados(c, *, tomador=None, servico=None, **extra):
    return {
        "tomador": (tomador or c.tomador).pk,
        "servico": (servico or c.exige).pk,
        "competencia": dt.date(2026, 10, 1),
        "valores": {"servico": "1000.00"},
        **extra,
    }


def _preparar(c, **extra):
    return servico_nfse.preparar(_dados(c, **extra), hoje=HOJE)


def _erros(c, **extra):
    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        _preparar(c, **extra)
    return erro.value.erros


def _rascunho(c, **extra):
    return servico_nfse.criar_rascunho(_dados(c, **extra), usuario=None, hoje=HOJE)


def _ibs(indicador, ind_dest):
    return {"codigo_indicador_operacao": indicador, "indicador_destinatario": ind_dest}


def _alterar_a_nota(nota, **campos):
    Nfse.objects.filter(pk=nota.pk).update(**campos)
    nota.refresh_from_db()


# -- prévia e rascunho --------------------------------------------------------------------------


def test_e0239_na_previa_barra_tomador_estrangeiro_com_a_regra_no_campo_tomador(cadastros):
    erros = _erros(cadastros, tomador=_tomador_de_fora(), ibs_cbs=_ibs(ADQUIRENTE, 0))

    assert "E0239" in erros["tomador"] and "100301" in erros["tomador"]
    assert "é estrangeiro" in erros["tomador"]


def test_e0239_barra_tomador_pj_sem_endereco_mesmo_com_indicador_do_servico(cadastros):
    erros = _erros(cadastros, tomador=_tomador_sem_endereco())

    assert "E0239" in erros["tomador"] and "falta o logradouro" in erros["tomador"]


def test_e0239_vale_tambem_quando_o_destinatario_e_outra_pessoa(cadastros):
    erros = _erros(
        cadastros,
        tomador=_tomador_de_fora(),
        ibs_cbs=_ibs(ADQUIRENTE, 1),
        destinatario=cadastros.destinatario.pk,
    )

    assert "E0239" in erros["tomador"] and "destinatario" not in erros


def test_rascunho_barrado_pela_regra_nao_e_gravado(cadastros):
    with pytest.raises(servico_nfse.ErroDeNota):
        _rascunho(cadastros, tomador=_tomador_de_fora())

    assert Nfse.objects.count() == 0


def test_e0239_aceita_tomador_pf_nacional(cadastros):
    pf = Pessoa.objects.create(
        tipo=Pessoa.Tipo.PESSOA_FISICA,
        documento=cpf_de_teste("529982247"),
        nome="TOMADOR PESSOA FISICA",
        logradouro="Rua das Palmeiras",
        numero="5",
        bairro="Centro",
        codigo_municipio="2903201",
        cep="47800000",
    )

    preparo = _preparar(cadastros, tomador=pf)

    assert preparo.complementos["ibs_cbs"]["codigo_indicador_operacao"] == ADQUIRENTE


def test_e0243_barra_tomador_estrangeiro_quando_o_local_e_o_do_destinatario(cadastros):
    erros = _erros(cadastros, tomador=_tomador_de_fora(), ibs_cbs=_ibs(DESTINATARIO, 0))

    assert "E0243" in erros["tomador"] and "próprio tomador" in erros["tomador"]


def test_e0243_aceita_tomador_nacional_completo(cadastros):
    preparo = _preparar(cadastros, ibs_cbs=_ibs(DESTINATARIO, 0))

    assert preparo.complementos["destinatario"] is None


def test_e0919_barra_destinatario_estrangeiro_e_olha_so_ele(cadastros):
    de_fora = criar_destinatario_de_teste(
        documento="",
        tipo=Pessoa.Tipo.ESTRANGEIRO,
        nif="NIF-1",
        nome="DESTINATARIO NO EXTERIOR",
        logradouro="Rue",
        numero="1",
        bairro="Centre",
        codigo_municipio="",
        cep="",
        pais="FR",
        codigo_postal="75001",
        cidade="Paris",
        estado="IDF",
    )

    erros = _erros(
        cadastros,
        tomador=_tomador_de_fora(),  # o tomador pode ser de fora: quem vale é o destinatário
        ibs_cbs=_ibs(DESTINATARIO, 1),
        destinatario=de_fora.pk,
    )

    assert "E0919" in erros["destinatario"] and "tomador" not in erros


def test_e0919_barra_destinatario_sem_endereco_nacional(cadastros):
    sem_endereco = Pessoa.objects.create(
        tipo=Pessoa.Tipo.PESSOA_JURIDICA,
        documento=cnpj_de_teste("054239600003"),
        nome="DESTINATARIO SEM ENDERECO",
    )

    erros = _erros(cadastros, ibs_cbs=_ibs(DESTINATARIO, 1), destinatario=sem_endereco.pk)

    assert "E0919" in erros["destinatario"] and "endereço incompleto" in erros["destinatario"]


def test_e0919_sem_destinatario_diz_a_regra_e_o_que_fazer(cadastros):
    erros = _erros(cadastros, ibs_cbs=_ibs(DESTINATARIO, 1))

    assert "E0919" in erros["destinatario"]
    assert "Escolha o destinatário no cadastro de pessoas" in erros["destinatario"]


def test_e0919_aceita_destinatario_nacional_e_o_dps_leva_os_dois(cadastros):
    preparo = _preparar(
        cadastros,
        tomador=_tomador_de_fora(),
        ibs_cbs=_ibs(DESTINATARIO, 1),
        destinatario=cadastros.destinatario.pk,
    )

    assert preparo.complementos["destinatario"]["dados"]["documento"] == (
        cadastros.destinatario.documento
    )


def test_destinatario_ruim_nao_importa_quando_o_local_e_o_do_adquirente(cadastros):
    sem_endereco = Pessoa.objects.create(
        tipo=Pessoa.Tipo.PESSOA_JURIDICA,
        documento=cnpj_de_teste("054239600004"),
        nome="DESTINATARIO SEM ENDERECO",
    )

    preparo = _preparar(cadastros, ibs_cbs=_ibs(ADQUIRENTE, 1), destinatario=sem_endereco.pk)

    assert preparo.complementos["destinatario"]["dados"]["nome"] == "DESTINATARIO SEM ENDERECO"


def test_indicador_sem_endereco_de_pessoa_nao_bloqueia_nem_com_tomador_de_fora(cadastros):
    preparo = _preparar(cadastros, tomador=_tomador_de_fora(), ibs_cbs=_ibs(OUTRO, 0))

    assert preparo.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO


@pytest.mark.parametrize("indicador", ["010104", "080101", "130101", "090101"])
def test_indicador_da_tabela_sem_marca_indnfse_nao_bloqueia(cadastros, indicador):
    """O critério de "fora da tabela" é constar do Anexo VII, não ter `indNFSe = S`."""
    preparo = _preparar(cadastros, tomador=_tomador_de_fora(), ibs_cbs=_ibs(indicador, 0))

    assert preparo.complementos["ibs_cbs"]["codigo_indicador_operacao"] == indicador


def test_e0901_indicador_fora_da_tabela_bloqueia(cadastros):
    erros = _erros(cadastros, ibs_cbs=_ibs("999999", 0))

    assert "E0901" in erros["ibs_cbs"] and "Anexo VII" in erros["ibs_cbs"]


def test_servico_sem_o_grupo_de_ibs_cbs_nao_aplica_nenhuma_regra(cadastros):
    """ind_gIBSCBS = 0: o grupo não vai na DPS, então tomador de fora não é barrado (E0239)."""
    preparo = _preparar(cadastros, tomador=_tomador_de_fora(), servico=cadastros.nao_exige)

    assert preparo.complementos["ibs_cbs"] is None
    assert preparo.ibs_cbs_dps["na_dps"] is False


def test_servico_sem_classificacao_nao_aplica_nenhuma_regra(cadastros):
    sem_classificacao = _servico("004", codigo_indicador_operacao=ADQUIRENTE)

    preparo = _preparar(cadastros, tomador=_tomador_de_fora(), servico=sem_classificacao)

    assert preparo.complementos["ibs_cbs"] is None


# -- 130201: aviso, nunca bloqueio --------------------------------------------------------------


def test_130201_avisa_na_conferencia_com_tomador_de_fora_sem_bloquear(cadastros):
    preparo = _preparar(cadastros, tomador=_tomador_de_fora(), ibs_cbs=_ibs("130201", 0))

    assert AVISO_130201 in preparo.avisos
    assert "E0239" in AVISO_130201 and "CPF/CNPJ" in AVISO_130201


def test_130201_avisa_com_tomador_sem_endereco(cadastros):
    preparo = _preparar(cadastros, tomador=_tomador_sem_endereco(), ibs_cbs=_ibs("130201", 0))

    assert AVISO_130201 in preparo.avisos


def test_130201_deixa_de_avisar_com_tomador_completo(cadastros):
    preparo = _preparar(cadastros, ibs_cbs=_ibs("130201", 0))

    assert AVISO_130201 not in preparo.avisos


def test_130201_com_aviso_cria_o_rascunho_e_a_emissao_segue(empresa_pronta, cadastros, sefin):
    nota = _rascunho(cadastros, tomador=_tomador_de_fora(), ibs_cbs=_ibs("130201", 0))

    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()

    assert nota.situacao == S.AUTORIZADA


def test_outro_indicador_de_outro_texto_nao_avisa(cadastros):
    preparo = _preparar(cadastros, tomador=_tomador_de_fora(), ibs_cbs=_ibs("090102", 0))

    assert AVISO_130201 not in preparo.avisos


# -- solicitação e execução ---------------------------------------------------------------------


def _tomador_de_fora_na_nota(nota):
    """O snapshot da nota passa a ser de um estrangeiro (como um rascunho anterior à regra)."""
    de_fora = _tomador_de_fora()
    _alterar_a_nota(nota, tomador=servico_nfse.snapshot_tomador(de_fora))


def test_rascunho_antigo_com_tomador_de_fora_e_barrado_na_solicitacao(
    empresa_pronta, cadastros, sefin
):
    nota = _rascunho(cadastros)
    _tomador_de_fora_na_nota(nota)

    with pytest.raises(emissao.ErroDeEmissao, match="E0239"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    nota.refresh_from_db()
    assert nota.situacao == S.RASCUNHO and sefin.total_de_posts == 0


def test_a_execucao_volta_a_rascunho_com_a_regra_na_mensagem_sem_enviar(
    empresa_pronta, cadastros, sefin
):
    nota = _rascunho(cadastros)
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    nota.refresh_from_db()
    _tomador_de_fora_na_nota(nota)

    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()

    assert nota.situacao == S.RASCUNHO and sefin.total_de_posts == 0
    assert "E0239" in nota.mensagem


def test_e0243_na_solicitacao(empresa_pronta, cadastros, sefin):
    nota = _rascunho(cadastros, ibs_cbs=_ibs(DESTINATARIO, 0))
    _tomador_de_fora_na_nota(nota)

    with pytest.raises(emissao.ErroDeEmissao, match="E0243"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    assert sefin.total_de_posts == 0


def test_e0919_na_solicitacao_e_na_execucao(empresa_pronta, cadastros, sefin):
    nota = _rascunho(
        cadastros, ibs_cbs=_ibs(DESTINATARIO, 1), destinatario=cadastros.destinatario.pk
    )
    de_fora = _tomador_de_fora()
    complementos = dict(nota.complementos)
    complementos["destinatario"] = {
        **complementos["destinatario"],
        "dados": servico_nfse.snapshot_tomador(de_fora),
    }
    _alterar_a_nota(nota, complementos=complementos)

    with pytest.raises(emissao.ErroDeEmissao, match="E0919"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    assert sefin.total_de_posts == 0

    # Se o dado estragar depois de a emissão ser pedida, a execução também barra.
    _alterar_a_nota(nota, situacao=S.ENVIANDO)
    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()
    assert nota.situacao == S.RASCUNHO and "E0919" in nota.mensagem
    assert sefin.total_de_posts == 0


def test_e0901_na_solicitacao_com_indicador_fora_da_tabela(empresa_pronta, cadastros, sefin):
    nota = _rascunho(cadastros)
    complementos = dict(nota.complementos)
    complementos["ibs_cbs_nota"] = {"codigo_indicador_operacao": "999999"}
    _alterar_a_nota(nota, complementos=complementos)

    with pytest.raises(emissao.ErroDeEmissao, match="E0901"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    assert sefin.total_de_posts == 0


def test_nota_sem_grupo_com_tomador_de_fora_emite(empresa_pronta, cadastros, sefin):
    nota = _rascunho(cadastros, tomador=_tomador_de_fora(), servico=cadastros.nao_exige)

    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()

    assert nota.situacao == S.AUTORIZADA


def test_nota_que_atende_a_regra_emite_normalmente(empresa_pronta, cadastros, sefin):
    nota = _rascunho(cadastros)

    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()

    assert nota.situacao == S.AUTORIZADA and sefin.total_de_posts == 1


# -- API ----------------------------------------------------------------------------------------


@pytest.fixture
def emissor_da_empresa(api_de, empresa_a):
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
        tomador, _ = criar_cadastros_de_teste()
        servico = _servico(
            "002", cst_ibs_cbs="000", c_class_trib=EXIGE, codigo_indicador_operacao=ADQUIRENTE
        )
        de_fora = _tomador_de_fora()
    corpo = {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": "2026-10-01",
        "valores": {"servico": "1500.00"},
    }
    return api_de(empresa_a, Perfil.EMISSOR), corpo, de_fora


def test_previa_pela_api_devolve_a_regra_no_campo_do_tomador(emissor_da_empresa):
    api, corpo, de_fora = emissor_da_empresa

    resposta = api.post(f"{NOTAS}previa/", {**corpo, "tomador": de_fora.pk})

    assert resposta.status_code == 400
    assert "E0239" in resposta.json()["tomador"]


def test_previa_pela_api_com_tomador_nacional_passa(emissor_da_empresa):
    api, corpo, _ = emissor_da_empresa

    assert api.post(f"{NOTAS}previa/", corpo).status_code == 200


def test_previa_pela_api_mostra_o_aviso_do_130201(emissor_da_empresa):
    api, corpo, de_fora = emissor_da_empresa

    resposta = api.post(
        f"{NOTAS}previa/",
        {**corpo, "tomador": de_fora.pk, "ibs_cbs": _ibs("130201", 0)},
    )

    assert resposta.status_code == 200, resposta.json()
    assert AVISO_130201 in resposta.json()["avisos"]


def test_criar_rascunho_pela_api_recusa_com_a_regra(emissor_da_empresa):
    api, corpo, de_fora = emissor_da_empresa

    resposta = api.post(NOTAS, {**corpo, "tomador": de_fora.pk})

    assert resposta.status_code == 400 and "E0239" in resposta.json()["tomador"]
