"""IBS/CBS pela classificação do serviço (issue #29, ADR 0010).

O grupo de IBS/CBS e o `cIndOp` são obrigatórios ou proibidos conforme o `ind_gIBSCBS` da
classificação tributária (cClassTrib) **do serviço** na data de competência (E0859/E0860); o
`cIndOp` é do serviço (Anexo VIII) e a nota e o modelo só o ajustam. Da empresa fica só o padrão do
destinatário (`indDest`). Todas as classificações usadas aqui constam da tabela oficial versionada.
"""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from django_tenants.utils import schema_context
from lxml import etree

from cadastros.models import Servico
from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal import gateway
from fiscal.models import ParametrosFiscais
from fiscal.services import emissao
from fiscal.services import nfse as servico_nfse
from fiscal.tests.apoio import criar_cadastros_de_teste, preparar_empresa_para_emitir

pytestmark = pytest.mark.django_db
HOJE = dt.date(2026, 10, 31)
NS = "{http://www.sped.fazenda.gov.br/nfse}"
NOTAS = "/api/fiscal/notas/"
PARAMETROS = "/api/fiscal/parametros/"
SERVICOS = "/api/cadastros/servicos/"
DO_SERVICO = "100301"  # Anexo VIII: item 01.01 + NBS 1.1502.10.00
AJUSTADO = "050101"
OUTRO = "050102"
EXIGE = "000001"  # ind_gIBSCBS = 1 (consta como válida para NFS-e)
NAO_EXIGE = "410009"  # ind_gIBSCBS = 0
NAO_VALE_PARA_NFSE = "200003"
ENCERRADA = "220001"  # só vigorou em 01/01/2026


# -- apoio ----------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """O município emissor é validado pela tabela de municípios (chamadas de parâmetros)."""


def _dados(tomador, servico, **extra):
    return {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": dt.date(2026, 10, 1),
        "valores": {"servico": "1000.00"},
        **extra,
    }


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
    """Tomador e serviços: sem classificação, que exige o grupo, que não exige, e que não vale."""
    tomador, sem = criar_cadastros_de_teste()
    exige = _servico(
        "002", cst_ibs_cbs="000", c_class_trib=EXIGE, codigo_indicador_operacao=DO_SERVICO
    )
    nao_exige = _servico(
        "003", cst_ibs_cbs="410", c_class_trib=NAO_EXIGE, codigo_indicador_operacao=DO_SERVICO
    )
    return SimpleNamespace(tomador=tomador, sem=sem, exige=exige, nao_exige=nao_exige)


def _preparar(tomador, servico, **extra):
    return servico_nfse.preparar(_dados(tomador, servico, **extra), hoje=HOJE)


def _erro(tomador, servico, **extra):
    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        _preparar(tomador, servico, **extra)
    return erro.value.erros


def _atualizar(servico, **campos):
    for campo, valor in campos.items():
        setattr(servico, campo, valor)
    servico.save()
    return servico


# -- a classificação do serviço decide se o grupo vai -----------------------------------------


def test_servico_sem_classificacao_sai_sem_grupo_e_sem_erro(cadastros):
    preparo = _preparar(cadastros.tomador, cadastros.sem)

    assert preparo.complementos["ibs_cbs"] is None
    assert preparo.ibs_cbs_dps["na_dps"] is False
    assert "Anexo VI não torna o grupo obrigatório" in preparo.ibs_cbs_dps["motivo"]
    assert not any("IBS/CBS" in aviso for aviso in preparo.avisos)


def test_classificacao_que_exige_o_grupo_leva_o_cindop_do_servico(cadastros):
    preparo = _preparar(cadastros.tomador, cadastros.exige)

    grupo = preparo.complementos["ibs_cbs"]
    assert grupo["codigo_indicador_operacao"] == DO_SERVICO
    assert grupo["indicador_destinatario"] == 0
    assert grupo["origens"] == {
        "codigo_indicador_operacao": "servico",
        "indicador_destinatario": "empresa",
    }
    dps = preparo.ibs_cbs_dps
    assert dps["na_dps"] is True and dps["motivo"] is None
    assert dps["regra"] == {"ind_gibscbs": True, "codigo": "E0860"}
    assert (dps["nbs"], dps["cst"], dps["c_class_trib"]) == ("115021000", "000", EXIGE)


def test_classificacao_sem_tributacao_de_ibs_cbs_nao_leva_o_grupo(cadastros):
    """E0859/E0961: com `ind_gIBSCBS = 0` o grupo e o cIndOp são proibidos, mesmo no serviço."""
    preparo = _preparar(cadastros.tomador, cadastros.nao_exige)

    assert preparo.complementos["ibs_cbs"] is None
    dps = preparo.ibs_cbs_dps
    assert dps["na_dps"] is False
    assert dps["regra"] == {"ind_gibscbs": False, "codigo": "E0859"}
    assert "ind_gIBSCBS = 0" in dps["motivo"] and NAO_EXIGE in dps["motivo"]


def test_ajuste_de_cindop_na_nota_e_ignorado_com_aviso_quando_a_classificacao_nao_exige(cadastros):
    preparo = _preparar(
        cadastros.tomador,
        cadastros.nao_exige,
        ibs_cbs={"codigo_indicador_operacao": AJUSTADO},
    )

    assert preparo.complementos["ibs_cbs"] is None
    assert any("não vai" in aviso and NAO_EXIGE in aviso for aviso in preparo.avisos)


def test_classificacao_que_exige_sem_cindop_no_servico_e_erro_e0860_que_manda_completar(
    cadastros,
):
    _atualizar(cadastros.exige, codigo_indicador_operacao="")

    erros = _erro(cadastros.tomador, cadastros.exige)

    assert "E0860" in erros["ibs_cbs"]
    assert "Complete o cadastro do serviço" in erros["ibs_cbs"] and "Anexo VIII" in erros["ibs_cbs"]


def test_o_ajuste_da_nota_supre_o_cindop_que_o_servico_nao_tem(cadastros):
    _atualizar(cadastros.exige, codigo_indicador_operacao="")

    preparo = _preparar(
        cadastros.tomador, cadastros.exige, ibs_cbs={"codigo_indicador_operacao": AJUSTADO}
    )

    grupo = preparo.complementos["ibs_cbs"]
    assert grupo["codigo_indicador_operacao"] == AJUSTADO
    assert grupo["origens"]["codigo_indicador_operacao"] == "nota"


def test_e0958_classificacao_que_nao_vale_para_nfse_e_erro(cadastros):
    servico = _servico("004", cst_ibs_cbs="200", c_class_trib=NAO_VALE_PARA_NFSE)

    erros = _erro(cadastros.tomador, servico)

    assert "E0958" in erros["ibs_cbs"] and "não vale para NFS-e" in erros["ibs_cbs"]


def test_e0958_classificacao_que_nao_consta_da_tabela_oficial_e_erro(cadastros):
    servico = _servico("004", cst_ibs_cbs="999", c_class_trib="999999")

    assert "não consta da tabela oficial" in _erro(cadastros.tomador, servico)["ibs_cbs"]


def test_classificacao_fora_da_vigencia_na_competencia_e_erro(cadastros):
    servico = _servico("004", cst_ibs_cbs="220", c_class_trib=ENCERRADA)

    assert "não vigora em 01/10/2026" in _erro(cadastros.tomador, servico)["ibs_cbs"]


def test_e0959_os_tres_primeiros_digitos_do_cclasstrib_devem_ser_o_cst(cadastros):
    _atualizar(cadastros.exige, cst_ibs_cbs="200")

    assert "E0959" in _erro(cadastros.tomador, cadastros.exige)["ibs_cbs"]


def test_competencia_anterior_a_tabela_oficial_sai_sem_grupo_com_aviso(cadastros):
    antigo = _servico(
        "006",
        cst_ibs_cbs="000",
        c_class_trib=EXIGE,
        codigo_indicador_operacao=DO_SERVICO,
        vigencia_inicio=dt.date(2025, 1, 1),
    )
    preparo = servico_nfse.preparar(
        _dados(cadastros.tomador, antigo, competencia=dt.date(2025, 12, 1)), hoje=HOJE
    )

    assert preparo.complementos["ibs_cbs"] is None
    assert any("01/01/2026" in aviso and "sem o grupo" in aviso for aviso in preparo.avisos)


def test_classificacao_incompleta_no_cadastro_antigo_e_erro_e0322(cadastros):
    _atualizar(cadastros.exige, nbs="")

    assert "E0322" in _erro(cadastros.tomador, cadastros.exige)["ibs_cbs"]


def test_e0902_servico_99_03_exige_cindop_02xxxx(cadastros):
    servico = _servico(
        "005",
        codigo_tributacao_nacional="990301",
        cst_ibs_cbs="000",
        c_class_trib=EXIGE,
        codigo_indicador_operacao=DO_SERVICO,
    )
    assert "E0902" in _erro(cadastros.tomador, servico)["ibs_cbs"]

    servico.codigo_indicador_operacao = "020101"
    servico.save()
    assert _preparar(cadastros.tomador, servico).complementos["ibs_cbs"] is not None


def test_cindop_fora_do_anexo_viii_nao_bloqueia_mas_avisa(cadastros):
    _atualizar(cadastros.exige, codigo_indicador_operacao="100101")

    preparo = _preparar(cadastros.tomador, cadastros.exige)

    assert preparo.complementos["ibs_cbs"]["codigo_indicador_operacao"] == "100101"
    assert any(
        "não consta do Anexo VIII" in aviso and DO_SERVICO in aviso for aviso in preparo.avisos
    )


def test_classificacao_fora_do_anexo_viii_para_o_indicador_avisa(cadastros):
    _atualizar(cadastros.exige, c_class_trib="000006")

    preparo = _preparar(cadastros.tomador, cadastros.exige)

    assert any("000006 não consta do Anexo VIII" in aviso for aviso in preparo.avisos)


def test_tomador_do_exterior_recebe_o_aviso_do_indop_equivalente(cadastros):
    servico = {
        "codigo_tributacao_nacional": "010101",
        "nbs": "115021000",
        "cst_ibs_cbs": "000",
        "c_class_trib": EXIGE,
        "codigo_indicador_operacao": DO_SERVICO,
    }
    erros, avisos = {}, []

    servico_nfse._ibs_cbs(
        None,
        None,
        servico,
        ParametrosFiscais.obter(),
        dt.date(2026, 10, 1),
        erros,
        avisos,
        adquirente_no_exterior=True,
    )

    assert not erros and any("100302" in aviso and "exterior" in aviso for aviso in avisos)


# -- as origens e a prioridade: nota > modelo > serviço (cIndOp); nota > modelo > empresa (indDest)


def _parametros(destinatario=0):
    return SimpleNamespace(ibs_cbs_indicador_destinatario=destinatario)


def _resolver(nota=None, modelo=None, indicador_do_servico=DO_SERVICO, destinatario=0):
    return servico_nfse.resolver_ibs_cbs(
        nota,
        modelo,
        {"codigo_indicador_operacao": indicador_do_servico},
        _parametros(destinatario),
    )


def test_sem_nota_nem_modelo_o_cindop_e_do_servico_e_o_destinatario_da_empresa():
    valores, origens, erro = _resolver(destinatario=1)

    assert erro is None
    assert valores == {"codigo_indicador_operacao": DO_SERVICO, "indicador_destinatario": 1}
    assert origens == {"codigo_indicador_operacao": "servico", "indicador_destinatario": "empresa"}


def test_o_modelo_vale_mais_que_o_servico_e_a_nota_vale_mais_que_o_modelo():
    modelo = {"codigo_indicador_operacao": AJUSTADO, "indicador_destinatario": 1}

    valores, origens, _ = _resolver(modelo=modelo)
    assert valores == {"codigo_indicador_operacao": AJUSTADO, "indicador_destinatario": 1}
    assert set(origens.values()) == {"modelo"}

    nota = {"codigo_indicador_operacao": OUTRO, "indicador_destinatario": 0}
    valores, origens, _ = _resolver(nota=nota, modelo=modelo)
    assert valores == {"codigo_indicador_operacao": OUTRO, "indicador_destinatario": 0}
    assert set(origens.values()) == {"nota"}


def test_cada_campo_e_resolvido_sozinho():
    valores, origens, _ = _resolver(
        nota={"indicador_destinatario": 1}, modelo={"codigo_indicador_operacao": AJUSTADO}
    )

    assert valores == {"codigo_indicador_operacao": AJUSTADO, "indicador_destinatario": 1}
    assert origens == {"codigo_indicador_operacao": "modelo", "indicador_destinatario": "nota"}


@pytest.mark.parametrize("vazio", [None, "", {}, {"codigo_indicador_operacao": ""}])
def test_vazio_nao_define_nada_e_o_servico_e_a_empresa_de_agora_e_que_valem(vazio):
    valores, origens, _ = _resolver(nota=vazio, modelo=vazio)

    assert valores["codigo_indicador_operacao"] == DO_SERVICO
    assert origens["codigo_indicador_operacao"] == "servico"


def test_a_chave_informar_de_antes_da_issue_29_e_ignorada():
    """Rascunhos e modelos antigos podem trazer `informar`: quem decide agora é a classificação."""
    valores, _, erro = _resolver(nota={"informar": False}, modelo={"informar": True})

    assert erro is None and valores["codigo_indicador_operacao"] == DO_SERVICO


@pytest.mark.parametrize(
    "nota", [{"indicador_destinatario": 2}, {"indicador_destinatario": "x"}], ids=["2", "texto"]
)
def test_destinatario_invalido_em_qualquer_nivel_e_recusado(nota):
    assert _resolver(nota=nota)[2] == "Informe se o destinatário é o próprio tomador (0 ou 1)."
    assert _resolver(modelo=nota)[2]


def test_o_ajuste_da_nota_guardado_so_tem_o_que_a_nota_definiu():
    assert servico_nfse.ajuste_da_nota({"codigo_indicador_operacao": OUTRO, "informar": True}) == {
        "codigo_indicador_operacao": OUTRO
    }
    assert servico_nfse.ajuste_da_nota({"indicador_destinatario": 1}) == {
        "indicador_destinatario": 1
    }
    assert servico_nfse.ajuste_da_nota({"codigo_indicador_operacao": ""}) is None
    assert servico_nfse.ajuste_da_nota(None) is None


def test_indicador_da_nota_com_formato_errado_e_recusado_na_emissao(cadastros):
    erros = _erro(
        cadastros.tomador, cadastros.exige, ibs_cbs={"codigo_indicador_operacao": "12345"}
    )

    assert "6 dígitos" in erros["ibs_cbs"]


# -- snapshot: a nota guarda o que valia quando nasceu -------------------------------------------


def test_rascunho_guarda_o_cindop_do_servico_e_so_muda_ao_ser_salvo_de_novo(cadastros):
    dados = _dados(cadastros.tomador, cadastros.exige)
    nota = servico_nfse.criar_rascunho(dados, usuario=None, hoje=HOJE)
    assert nota.servico["codigo_indicador_operacao"] == DO_SERVICO

    _atualizar(cadastros.exige, codigo_indicador_operacao=OUTRO)
    nota.refresh_from_db()
    assert nota.servico["codigo_indicador_operacao"] == DO_SERVICO  # a nota não muda sozinha

    servico_nfse.atualizar_rascunho(nota, dados)
    assert nota.servico["codigo_indicador_operacao"] == OUTRO


def test_substituta_leva_o_mesmo_grupo_da_original(cadastros):
    from fiscal.models import Nfse

    original = servico_nfse.criar_rascunho(
        _dados(cadastros.tomador, cadastros.exige), usuario=None, hoje=HOJE
    )
    Nfse.objects.filter(pk=original.pk).update(situacao=Nfse.Situacao.AUTORIZADA, chave="1" * 50)
    original.refresh_from_db()

    substituta = servico_nfse.criar_substituta(
        original, codigo_motivo="01", motivo="", usuario=None
    )

    assert substituta.complementos["ibs_cbs"] == original.complementos["ibs_cbs"]


# -- o que chega à DPS ------------------------------------------------------------------------


def _emitir(empresa, nota):
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    return etree.fromstring(bytes(nota.xml_dps))


def test_dps_assinada_leva_o_grupo_com_o_cindop_do_servico_e_a_classificacao(
    empresa_pronta, cadastros, sefin
):
    nota = servico_nfse.criar_rascunho(
        _dados(cadastros.tomador, cadastros.exige), usuario=None, hoje=HOJE
    )

    raiz = _emitir(empresa_pronta, nota)

    grupo = raiz.find(f".//{NS}IBSCBS")
    assert grupo is not None
    assert grupo.findtext(f"{NS}cIndOp") == DO_SERVICO
    assert grupo.findtext(f"{NS}indDest") == "0"
    assert grupo.findtext(f"{NS}valores/{NS}trib/{NS}CST") == "000"
    assert grupo.findtext(f"{NS}valores/{NS}trib/{NS}cClassTrib") == EXIGE
    assert raiz.findtext(f".//{NS}cNBS") == "115021000"


def test_dps_assinada_leva_o_ajuste_da_nota_e_nao_o_do_servico(empresa_pronta, cadastros, sefin):
    nota = servico_nfse.criar_rascunho(
        _dados(
            cadastros.tomador,
            cadastros.exige,
            ibs_cbs={"codigo_indicador_operacao": AJUSTADO, "indicador_destinatario": 1},
        ),
        usuario=None,
        hoje=HOJE,
    )

    grupo = _emitir(empresa_pronta, nota).find(f".//{NS}IBSCBS")

    assert grupo.findtext(f"{NS}cIndOp") == AJUSTADO
    assert grupo.findtext(f"{NS}indDest") == "1"


def test_dps_assinada_nao_leva_o_grupo_quando_a_classificacao_nao_exige(
    empresa_pronta, cadastros, sefin
):
    for servico in (cadastros.sem, cadastros.nao_exige):
        nota = servico_nfse.criar_rascunho(
            _dados(cadastros.tomador, servico), usuario=None, hoje=HOJE
        )

        raiz = _emitir(empresa_pronta, nota)

        assert raiz.find(f".//{NS}IBSCBS") is None
        assert raiz.find(f".//{NS}cIndOp") is None


def test_rascunho_antigo_sem_cindop_no_snapshot_e_barrado_antes_de_ir_a_sefin(
    empresa_pronta, cadastros, sefin
):
    """Um rascunho de antes da regra, para um serviço que agora exige o grupo, não é enviado."""
    nota = servico_nfse.criar_rascunho(
        _dados(cadastros.tomador, cadastros.exige), usuario=None, hoje=HOJE
    )
    nota.servico = {**nota.servico, "codigo_indicador_operacao": ""}
    nota.save()

    with pytest.raises(emissao.ErroDeEmissao, match="E0860"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    assert sefin.total_de_posts == 0


def test_montar_dps_traduz_o_grupo_decidido(cadastros):
    nota = servico_nfse.criar_rascunho(
        _dados(cadastros.tomador, cadastros.exige), usuario=None, hoje=HOJE
    )
    dados = servico_nfse.dados_da_dps(
        nota, empresa=SimpleNamespace(cnpj="11222333000181"), numero=1
    )

    dps = gateway.montar_dps(dados)

    assert (dps.ibs_cbs.codigo_indicador_operacao, dps.ibs_cbs.indicador_destinatario) == (
        DO_SERVICO,
        0,
    )
    assert (dps.ibs_cbs.cst, dps.ibs_cbs.codigo_classificacao) == ("000", EXIGE)


# -- parâmetros da empresa (API): sobra só o destinatário ---------------------------------------


@pytest.fixture
def api_admin(api_de, empresa_a):
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
    return api_de(empresa_a)


def test_parametros_nao_trazem_mais_a_opcao_nem_o_indicador_da_empresa(api_admin):
    corpo = api_admin.get(PARAMETROS).json()

    assert "ibs_cbs_informar" not in corpo and "ibs_cbs_indicador_operacao" not in corpo
    assert corpo["ibs_cbs_indicador_destinatario"] == 0


def test_campos_antigos_enviados_por_clientes_defasados_sao_ignorados(api_admin):
    resposta = api_admin.patch(
        PARAMETROS, {"ibs_cbs_informar": True, "ibs_cbs_indicador_operacao": "010101"}
    )

    assert resposta.status_code == 200, resposta.json()
    assert "ibs_cbs_informar" not in resposta.json()


def test_administrador_muda_o_destinatario_padrao_da_empresa_e_a_mudanca_e_auditada(api_admin):
    resposta = api_admin.patch(PARAMETROS, {"ibs_cbs_indicador_destinatario": 1})

    assert resposta.status_code == 200, resposta.json()
    assert resposta.json()["ibs_cbs_indicador_destinatario"] == 1
    log = LogAuditoria.objects.filter(acao=LogAuditoria.Acao.PARAMETROS_ALTERADOS).last()
    assert "ibs_cbs_indicador_destinatario" in str(log.detalhes)


def test_destinatario_padrao_da_empresa_so_aceita_0_ou_1(api_admin):
    assert api_admin.patch(PARAMETROS, {"ibs_cbs_indicador_destinatario": 2}).status_code == 400


@pytest.mark.parametrize("perfil", [Perfil.EMISSOR, Perfil.CONSULTA, Perfil.FINANCEIRO])
def test_so_quem_edita_a_configuracao_muda_o_destinatario_padrao(api_de, empresa_a, perfil):
    resposta = api_de(empresa_a, perfil).patch(PARAMETROS, {"ibs_cbs_indicador_destinatario": 1})

    assert resposta.status_code == 403


def test_prontidao_expoe_so_o_destinatario_padrao_para_a_tela(api_de, empresa_a):
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
        ParametrosFiscais.objects.update(ibs_cbs_indicador_destinatario=1)

    corpo = api_de(empresa_a, Perfil.EMISSOR).get(f"{NOTAS}prontidao/").json()

    assert corpo["ibs_cbs"] == {"indicador_destinatario": 1}


# -- prévia e criação pela API --------------------------------------------------------------


@pytest.fixture
def emissor_com_servico(api_de, empresa_a):
    """Emissor da empresa A (pronta) e o corpo de uma nota de serviço que **exige** o grupo."""
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
        tomador, _ = criar_cadastros_de_teste()
        servico = _servico(
            "002", cst_ibs_cbs="000", c_class_trib=EXIGE, codigo_indicador_operacao=DO_SERVICO
        )
    corpo = {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": "2026-10-01",
        "valores": {"servico": "1500.00"},
    }
    return api_de(empresa_a, Perfil.EMISSOR), corpo


def test_previa_mostra_o_que_vai_na_dps_com_a_origem_e_a_regra(emissor_com_servico):
    api, corpo = emissor_com_servico

    previa = api.post(f"{NOTAS}previa/", corpo).json()["ibs_cbs"]

    assert previa["na_dps"] is True
    assert previa["codigo_indicador_operacao"] == DO_SERVICO
    assert previa["origens"]["codigo_indicador_operacao"] == "servico"
    assert previa["regra"] == {"ind_gibscbs": True, "codigo": "E0860"}


def test_previa_com_ajuste_pontual_mostra_a_nota_como_origem(emissor_com_servico):
    api, corpo = emissor_com_servico

    previa = api.post(
        f"{NOTAS}previa/", {**corpo, "ibs_cbs": {"codigo_indicador_operacao": AJUSTADO}}
    ).json()["ibs_cbs"]

    assert previa["codigo_indicador_operacao"] == AJUSTADO
    assert previa["origens"]["codigo_indicador_operacao"] == "nota"


def test_previa_recusa_ajuste_invalido_com_a_mensagem_no_campo(emissor_com_servico):
    api, corpo = emissor_com_servico

    resposta = api.post(f"{NOTAS}previa/", {**corpo, "ibs_cbs": {"codigo_indicador_operacao": "1"}})

    assert resposta.status_code == 400
    assert "6 dígitos" in resposta.json()["ibs_cbs"]


def test_previa_diz_por_que_o_grupo_nao_vai(api_de, empresa_a):
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
        tomador, _ = criar_cadastros_de_teste()
        servico = _servico("003", cst_ibs_cbs="410", c_class_trib=NAO_EXIGE)
    corpo = {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": "2026-10-01",
        "valores": {"servico": "100.00"},
    }

    previa = api_de(empresa_a, Perfil.EMISSOR).post(f"{NOTAS}previa/", corpo).json()["ibs_cbs"]

    assert previa["na_dps"] is False and "ind_gIBSCBS = 0" in previa["motivo"]


def test_nota_criada_pela_api_guarda_o_ajuste_e_a_origem(emissor_com_servico):
    api, corpo = emissor_com_servico

    resposta = api.post(NOTAS, {**corpo, "ibs_cbs": {"codigo_indicador_operacao": AJUSTADO}})

    assert resposta.status_code == 201, resposta.json()
    complementos = resposta.json()["complementos"]
    assert complementos["ibs_cbs"]["codigo_indicador_operacao"] == AJUSTADO
    assert complementos["ibs_cbs_nota"] == {"codigo_indicador_operacao": AJUSTADO}


# -- cadastro do serviço (API) --------------------------------------------------------------


@pytest.fixture
def api_servicos(api_de, empresa_a):
    return api_de(empresa_a)


def _referencias(api, **params):
    return api.get(f"{SERVICOS}referencias-ibs-cbs/" + (f"?{urlencode(params)}" if params else ""))


def _corpo_do_servico(**campos):
    return {
        "nome": "Análise de sistemas",
        "descricao": "Análise e desenvolvimento de sistemas.",
        "codigo_tributacao_nacional": "01.01.01",
        "codigo_tributacao_municipal": "007",
        "nbs": "1.1502.10.00",
        "cst_ibs_cbs": "000",
        "c_class_trib": EXIGE,
        "codigo_indicador_operacao": DO_SERVICO,
        "aliquota_iss": "2.00",
        "vigencia_inicio": "2026-01-01",
        **campos,
    }


def test_servico_guarda_o_cindop(api_servicos):
    resposta = api_servicos.post(SERVICOS, _corpo_do_servico(codigo_indicador_operacao="100.301"))

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["codigo_indicador_operacao"] == DO_SERVICO


@pytest.mark.parametrize("indicador", ["12345", "1234567"])
def test_servico_recusa_cindop_com_formato_errado(api_servicos, indicador):
    resposta = api_servicos.post(SERVICOS, _corpo_do_servico(codigo_indicador_operacao=indicador))

    assert resposta.status_code == 400
    assert "6 dígitos" in resposta.json()["codigo_indicador_operacao"][0]


def test_servico_99_03_recusa_cindop_fora_do_grupo_02(api_servicos):
    resposta = api_servicos.post(SERVICOS, _corpo_do_servico(codigo_tributacao_nacional="990301"))

    assert resposta.status_code == 400
    assert "E0902" in resposta.json()["codigo_indicador_operacao"][0]
    ok = api_servicos.post(
        SERVICOS,
        _corpo_do_servico(codigo_tributacao_nacional="990301", codigo_indicador_operacao="020101"),
    )
    assert ok.status_code == 201, ok.json()


def test_servico_recusa_cclasstrib_que_nao_comeca_pelo_cst(api_servicos):
    resposta = api_servicos.post(SERVICOS, _corpo_do_servico(cst_ibs_cbs="200"))

    assert resposta.status_code == 400
    assert "E0959" in resposta.json()["c_class_trib"][0]


def test_referencias_sugerem_o_cindop_do_anexo_viii_e_dizem_se_a_classificacao_exige(api_servicos):
    resposta = _referencias(
        api_servicos,
        **{
            "codigo_nacional": "01.01.01",
            "nbs": "1.1502.10.00",
            "c_class_trib": EXIGE,
            "data": "2026-10-01",
        },
    )

    corpo = resposta.json()
    assert resposta.status_code == 200, corpo
    assert corpo["indop"]["sugestao"] == DO_SERVICO and corpo["indop"]["encontrado"] is True
    assert corpo["indop"]["locais"][DO_SERVICO] == "Domicílio principal do adquirente"
    assert EXIGE in corpo["indop"]["classes_possiveis"]
    assert corpo["classificacao"]["exige_grupo_ibs_cbs"] is True
    assert "exige o grupo de IBS/CBS" in corpo["classificacao"]["mensagem"]


def test_referencias_com_varias_opcoes_nao_escolhem_pelo_usuario(api_servicos):
    corpo = _referencias(api_servicos, **{"codigo_nacional": "010701", "nbs": "115013000"}).json()

    assert corpo["indop"]["sugestao"] is None
    assert corpo["indop"]["opcoes"] == ["050101", "050102", "100301"]


@pytest.mark.parametrize(
    ("classificacao", "trecho"),
    [
        (NAO_EXIGE, "não tem tributação de IBS/CBS"),
        (NAO_VALE_PARA_NFSE, "não vale para NFS-e"),
        ("999999", "não consta da tabela oficial"),
        (ENCERRADA, "não vigora em 01/10/2026"),
    ],
)
def test_referencias_explicam_a_situacao_de_cada_classificacao(api_servicos, classificacao, trecho):
    corpo = _referencias(
        api_servicos, **{"c_class_trib": classificacao, "data": "2026-10-01"}
    ).json()

    assert trecho in corpo["classificacao"]["mensagem"]


def test_referencias_sem_parametros_respondem_vazio(api_servicos):
    assert _referencias(api_servicos).json() == {
        "indop": None,
        "classificacao": None,
    }


def test_referencias_so_pedem_a_permissao_de_consulta(api_de, empresa_a):
    resposta = _referencias(api_de(empresa_a, Perfil.CONSULTA))

    assert resposta.status_code == 200
