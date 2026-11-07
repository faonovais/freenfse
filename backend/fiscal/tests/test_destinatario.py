"""Destinatário do serviço na nota (issue #33, ADR 0011).

Com `indDest = 1` (o destinatário não é o próprio tomador) e o grupo de IBS/CBS na DPS, a nota
precisa dizer quem é o destinatário: uma pessoa do cadastro, escolhida na nota ou no modelo. Vai
na DPS como grupo `dest`, copiada (snapshot) como o tomador. Com `indDest = 0`, ou sem grupo, é
descartado. As regras de endereço (E0239, E0243, E0919) estão em `test_regras_de_endereco.py`.
"""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django_tenants.utils import schema_context
from lxml import etree

from cadastros.models import Pessoa, Servico
from conftest import cnpj_de_teste, cpf_de_teste
from core.permissoes import Perfil
from fiscal.models import Nfse
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
NS = "{http://www.sped.fazenda.gov.br/nfse}"
NOTAS = "/api/fiscal/notas/"
DO_SERVICO = "100301"  # Anexo VIII: item 01.01 + NBS 1.1502.10.00; local = endereço do tomador
EXIGE, NAO_EXIGE = "000001", "410009"
OUTRA_PESSOA = {"indicador_destinatario": 1}
O_PROPRIO_TOMADOR = {"indicador_destinatario": 0}


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """A tabela de municípios valida o município do emissor."""


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
    """Tomador, o serviço que exige o grupo, o que não exige e um destinatário."""
    tomador, _ = criar_cadastros_de_teste()
    exige = _servico(
        "002", cst_ibs_cbs="000", c_class_trib=EXIGE, codigo_indicador_operacao=DO_SERVICO
    )
    nao_exige = _servico(
        "003", cst_ibs_cbs="410", c_class_trib=NAO_EXIGE, codigo_indicador_operacao=DO_SERVICO
    )
    return SimpleNamespace(
        tomador=tomador,
        exige=exige,
        nao_exige=nao_exige,
        destinatario=criar_destinatario_de_teste(),
    )


def _dados(c, servico=None, **extra):
    return {
        "tomador": c.tomador.pk,
        "servico": (servico or c.exige).pk,
        "competencia": dt.date(2026, 10, 1),
        "valores": {"servico": "1000.00"},
        **extra,
    }


def _preparar(c, servico=None, **extra):
    return servico_nfse.preparar(_dados(c, servico, **extra), hoje=HOJE)


def _erros(c, servico=None, **extra):
    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        _preparar(c, servico, **extra)
    return erro.value.erros


def _rascunho(c, servico=None, **extra):
    return servico_nfse.criar_rascunho(_dados(c, servico, **extra), usuario=None, hoje=HOJE)


def _emitir(empresa, nota):
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    return nota


def _dest(sefin):
    """O grupo `dest` da última DPS (assinada) recebida pela Sefin; `None` se não foi enviado."""
    raiz = etree.fromstring(sefin.dps_recebidas[-1])
    return next(raiz.iter(NS + "dest"), None)


# -- obrigatório com indDest = 1 -------------------------------------------------------------


def test_outra_pessoa_sem_destinatario_e_recusada_dizendo_o_que_fazer(cadastros):
    erros = _erros(cadastros, ibs_cbs=OUTRA_PESSOA)

    assert "destinatario" in erros
    assert (
        "outra pessoa" in erros["destinatario"]
        and "Escolha o destinatário" in erros["destinatario"]
    )


def test_outra_pessoa_com_destinatario_guarda_a_copia_e_a_origem(cadastros):
    d = cadastros.destinatario

    preparo = _preparar(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=d.pk)

    info = preparo.complementos["destinatario"]
    assert info["pessoa"] == d.pk and info["origem"] == "nota"
    assert info["dados"]["nome"] == d.nome and info["dados"]["documento"] == d.documento
    assert info["dados"]["codigo_municipio"] == d.codigo_municipio
    assert preparo.complementos["destinatario_nota"] == d.pk
    assert not any("destinatário" in aviso for aviso in preparo.avisos)


def test_destinatario_herdado_da_empresa_tambem_e_obrigatorio(cadastros):
    from fiscal.models import ParametrosFiscais

    ParametrosFiscais.objects.update(ibs_cbs_indicador_destinatario=1)

    assert "destinatario" in _erros(cadastros)  # sem ajuste na nota: indDest = 1 vem da empresa


def test_destinatario_inexistente_ou_inativo_e_recusado(cadastros):
    inativo = criar_destinatario_de_teste(
        documento=cnpj_de_teste("054239600002"), nome="INATIVO LTDA", ativo=False
    )

    assert "ativo" in _erros(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=99999)["destinatario"]
    assert (
        "ativo" in _erros(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=inativo.pk)["destinatario"]
    )


def test_nome_do_destinatario_acima_de_150_caracteres_e_recusado_antes_da_dps(cadastros):
    longo = criar_destinatario_de_teste(documento=cnpj_de_teste("054239600003"), nome="N" * 151)

    erro = _erros(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=longo.pk)["destinatario"]

    assert "150" in erro


def test_destinatario_igual_ao_tomador_passa_com_aviso(cadastros):
    preparo = _preparar(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=cadastros.tomador.pk)

    assert any("próprio tomador" in aviso for aviso in preparo.avisos)


# -- descartado com indDest = 0 ou sem grupo --------------------------------------------------


def test_o_proprio_tomador_descarta_o_destinatario_escolhido_e_avisa(cadastros):
    preparo = _preparar(
        cadastros, ibs_cbs=O_PROPRIO_TOMADOR, destinatario=cadastros.destinatario.pk
    )

    assert preparo.complementos["destinatario"] is None
    assert preparo.complementos["destinatario_nota"] is None  # "limpo" com indDest = 0
    assert any("não vai na nota" in aviso for aviso in preparo.avisos)


def test_sem_destinatario_e_com_o_proprio_tomador_nao_ha_aviso_nem_erro(cadastros):
    preparo = _preparar(cadastros, ibs_cbs=O_PROPRIO_TOMADOR)

    assert preparo.complementos["destinatario"] is None
    assert not any("destinatário" in aviso for aviso in preparo.avisos)


def test_servico_sem_grupo_de_ibs_cbs_nao_pede_nem_leva_destinatario(cadastros):
    preparo = _preparar(
        cadastros, cadastros.nao_exige, ibs_cbs=OUTRA_PESSOA, destinatario=cadastros.destinatario.pk
    )

    assert preparo.complementos["ibs_cbs"] is None
    assert preparo.complementos["destinatario"] is None
    sem_escolha = _preparar(cadastros, cadastros.nao_exige, ibs_cbs=OUTRA_PESSOA)
    assert sem_escolha.complementos["destinatario"] is None  # e não é erro


# -- modelo: nota > modelo -------------------------------------------------------------------


def test_o_modelo_define_o_destinatario_e_a_nota_pode_trocar(cadastros):
    do_modelo = cadastros.destinatario
    da_nota = criar_destinatario_de_teste(documento=cnpj_de_teste("054239600004"), nome="DA NOTA")

    herdado = _preparar(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario_modelo=do_modelo.pk)
    trocado = _preparar(
        cadastros, ibs_cbs=OUTRA_PESSOA, destinatario_modelo=do_modelo.pk, destinatario=da_nota.pk
    )

    assert herdado.complementos["destinatario"]["origem"] == "modelo"
    assert herdado.complementos["destinatario"]["pessoa"] == do_modelo.pk
    assert herdado.complementos["destinatario_nota"] is None
    assert trocado.complementos["destinatario"]["origem"] == "nota"
    assert trocado.complementos["destinatario"]["pessoa"] == da_nota.pk
    assert trocado.complementos["destinatario_modelo"] == do_modelo.pk  # o modelo segue guardado


def test_corrigir_o_rascunho_mantem_o_do_modelo_e_limpar_a_escolha_volta_a_ele(cadastros):
    d = cadastros.destinatario
    outro = criar_destinatario_de_teste(documento=cnpj_de_teste("054239600005"), nome="OUTRO")
    nota = _rascunho(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario_modelo=d.pk)

    servico_nfse.atualizar_rascunho(
        nota, _dados(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=outro.pk)
    )
    assert nota.complementos["destinatario"]["pessoa"] == outro.pk
    assert nota.complementos["destinatario_modelo"] == d.pk

    servico_nfse.atualizar_rascunho(
        nota, _dados(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=None)
    )
    assert nota.complementos["destinatario"]["origem"] == "modelo"
    assert nota.complementos["destinatario"]["pessoa"] == d.pk


# -- snapshot ---------------------------------------------------------------------------------


def test_mudar_o_cadastro_depois_nao_muda_o_destinatario_da_nota(cadastros):
    d = cadastros.destinatario
    nota = _rascunho(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=d.pk)

    d.nome = "NOME NOVO LTDA"
    d.save()
    nota.refresh_from_db()

    assert nota.complementos["destinatario"]["dados"]["nome"] == "DESTINATARIO FICTICIO LTDA"
    dados = servico_nfse.dados_da_dps(nota, empresa=SimpleNamespace(cnpj="11222333000181"))
    assert dados["destinatario"]["nome"] == "DESTINATARIO FICTICIO LTDA"


# -- DPS assinada -----------------------------------------------------------------------------


def test_dps_assinada_leva_o_grupo_dest_quando_a_nota_tem_outro_destinatario(
    empresa_pronta, cadastros, sefin
):
    d = cadastros.destinatario
    nota = _rascunho(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=d.pk)

    nota = _emitir(empresa_pronta, nota)

    assert nota.situacao == S.AUTORIZADA
    dest = _dest(sefin)
    assert dest is not None
    assert dest.findtext(f"{NS}CNPJ") == d.documento
    assert dest.findtext(f"{NS}xNome") == d.nome
    assert dest.findtext(f"{NS}end/{NS}endNac/{NS}cMun") == d.codigo_municipio
    assert dest.findtext(f"{NS}end/{NS}endNac/{NS}CEP") == d.cep
    assert dest.findtext(f"{NS}end/{NS}xLgr") == d.logradouro
    raiz = etree.fromstring(sefin.dps_recebidas[-1])
    assert raiz.findtext(f".//{NS}IBSCBS/{NS}indDest") == "1"


def test_dps_assinada_nao_leva_o_dest_quando_o_destinatario_e_o_proprio_tomador(
    empresa_pronta, cadastros, sefin
):
    nota = _rascunho(cadastros, ibs_cbs=O_PROPRIO_TOMADOR, destinatario=cadastros.destinatario.pk)

    nota = _emitir(empresa_pronta, nota)

    assert nota.situacao == S.AUTORIZADA
    assert _dest(sefin) is None
    raiz = etree.fromstring(sefin.dps_recebidas[-1])
    assert raiz.findtext(f".//{NS}IBSCBS/{NS}indDest") == "0"


def test_se_o_padrao_da_empresa_muda_para_o_proprio_tomador_a_dps_sai_sem_dest(
    empresa_pronta, cadastros, sefin
):
    """Rascunho com indDest = 1 (da empresa): o envio reavalia e descarta o destinatário."""
    from fiscal.models import ParametrosFiscais

    ParametrosFiscais.objects.update(ibs_cbs_indicador_destinatario=1)
    nota = _rascunho(cadastros, destinatario=cadastros.destinatario.pk)
    assert nota.complementos["destinatario"] is not None
    ParametrosFiscais.objects.update(ibs_cbs_indicador_destinatario=0)

    nota = _emitir(empresa_pronta, nota)

    assert nota.situacao == S.AUTORIZADA
    assert _dest(sefin) is None
    raiz = etree.fromstring(sefin.dps_recebidas[-1])
    assert raiz.findtext(f".//{NS}IBSCBS/{NS}indDest") == "0"


def test_dps_assinada_leva_destinatario_estrangeiro_com_nif(empresa_pronta, cadastros, sefin):
    estrangeiro = criar_destinatario_de_teste(
        tipo=Pessoa.Tipo.ESTRANGEIRO,
        documento="",
        nif="DE123456789",
        nome="EMPRESA ESTRANGEIRA GMBH",
        logradouro="Hauptstrasse",
        numero="1",
        bairro="Mitte",
        codigo_municipio="",
        cep="",
        pais="DE",
        codigo_postal="10115",
        cidade="Berlin",
        estado="BE",
    )
    nota = _rascunho(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=estrangeiro.pk)

    nota = _emitir(empresa_pronta, nota)

    assert nota.situacao == S.AUTORIZADA
    dest = _dest(sefin)
    assert dest.findtext(f"{NS}NIF") == "DE123456789"
    assert dest.findtext(f"{NS}end/{NS}endExt/{NS}cPais") == "DE"


def test_dps_assinada_leva_destinatario_pessoa_fisica_com_cpf(empresa_pronta, cadastros, sefin):
    pf = criar_destinatario_de_teste(
        tipo=Pessoa.Tipo.PESSOA_FISICA, documento=cpf_de_teste("123456789"), nome="MARIA FICTICIA"
    )
    nota = _rascunho(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=pf.pk)

    _emitir(empresa_pronta, nota)

    assert _dest(sefin).findtext(f"{NS}CPF") == pf.documento


# -- solicitação e execução reavaliam ---------------------------------------------------------


def test_rascunho_antigo_com_outra_pessoa_e_sem_destinatario_e_barrado_na_solicitacao(
    empresa_pronta, cadastros, sefin
):
    nota = _rascunho(cadastros, ibs_cbs=O_PROPRIO_TOMADOR)
    # Como um rascunho de antes da correção: indDest = 1 gravado, sem nenhum destinatário.
    complementos = dict(nota.complementos)
    complementos["ibs_cbs_nota"] = OUTRA_PESSOA
    Nfse.objects.filter(pk=nota.pk).update(complementos=complementos)
    nota.refresh_from_db()

    with pytest.raises(emissao.ErroDeEmissao, match="destinatário"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    assert sefin.total_de_posts == 0


def test_se_o_destinatario_some_da_nota_a_execucao_volta_a_rascunho_sem_enviar(
    empresa_pronta, cadastros, sefin
):
    nota = _rascunho(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=cadastros.destinatario.pk)
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    nota.refresh_from_db()
    complementos = dict(nota.complementos)
    complementos["destinatario"] = None
    Nfse.objects.filter(pk=nota.pk).update(complementos=complementos)

    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()

    assert nota.situacao == S.RASCUNHO and sefin.total_de_posts == 0
    assert "destinatário" in nota.mensagem


def test_a_nota_substituta_leva_o_mesmo_destinatario(empresa_pronta, cadastros, sefin):
    nota = _emitir(
        empresa_pronta,
        _rascunho(cadastros, ibs_cbs=OUTRA_PESSOA, destinatario=cadastros.destinatario.pk),
    )

    substituta = servico_nfse.criar_substituta(
        nota, codigo_motivo="99", motivo="Correção de dados da nota original.", usuario=None
    )
    substituta = _emitir(empresa_pronta, substituta)

    assert substituta.situacao == S.AUTORIZADA
    assert _dest(sefin).findtext(f"{NS}CNPJ") == cadastros.destinatario.documento


# -- API --------------------------------------------------------------------------------------


@pytest.fixture
def emissor_da_empresa(api_de, empresa_a):
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
        tomador, _ = criar_cadastros_de_teste()
        servico = _servico(
            "002", cst_ibs_cbs="000", c_class_trib=EXIGE, codigo_indicador_operacao=DO_SERVICO
        )
        destinatario = criar_destinatario_de_teste()
    corpo = {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": "2026-10-01",
        "valores": {"servico": "1500.00"},
    }
    return api_de(empresa_a, Perfil.EMISSOR), corpo, destinatario


def test_previa_pela_api_mostra_o_destinatario_escolhido(emissor_da_empresa):
    api, corpo, destinatario = emissor_da_empresa

    resposta = api.post(
        f"{NOTAS}previa/", {**corpo, "ibs_cbs": OUTRA_PESSOA, "destinatario": destinatario.pk}
    )

    assert resposta.status_code == 200, resposta.json()
    info = resposta.json()["complementos"]["destinatario"]
    assert info["origem"] == "nota" and info["dados"]["nome"] == destinatario.nome


def test_previa_pela_api_recusa_outra_pessoa_sem_destinatario_com_a_mensagem_no_campo(
    emissor_da_empresa,
):
    api, corpo, _ = emissor_da_empresa

    resposta = api.post(f"{NOTAS}previa/", {**corpo, "ibs_cbs": OUTRA_PESSOA})

    assert resposta.status_code == 400
    assert "Escolha o destinatário" in resposta.json()["destinatario"]


def test_criar_e_corrigir_rascunho_pela_api_guardam_o_destinatario(emissor_da_empresa):
    api, corpo, destinatario = emissor_da_empresa

    criada = api.post(NOTAS, {**corpo, "ibs_cbs": OUTRA_PESSOA, "destinatario": destinatario.pk})

    assert criada.status_code == 201, criada.json()
    complementos = criada.json()["complementos"]
    assert complementos["destinatario_nota"] == destinatario.pk
    assert complementos["destinatario"]["dados"]["documento"] == destinatario.documento

    corrigida = api.patch(f"{NOTAS}{criada.json()['id']}/", {**corpo, "ibs_cbs": O_PROPRIO_TOMADOR})
    assert corrigida.status_code == 200, corrigida.json()
    assert corrigida.json()["complementos"]["destinatario"] is None
    assert corrigida.json()["complementos"]["destinatario_nota"] is None


def test_a_entrada_aceita_destinatario_nulo_ou_ausente(emissor_da_empresa):
    api, corpo, _ = emissor_da_empresa

    com_nulo = api.post(
        f"{NOTAS}previa/", {**corpo, "ibs_cbs": O_PROPRIO_TOMADOR, "destinatario": None}
    )
    sem_campo = api.post(f"{NOTAS}previa/", {**corpo, "ibs_cbs": O_PROPRIO_TOMADOR})

    assert com_nulo.status_code == 200 and sem_campo.status_code == 200
