"""`pAliq` na DPS assinada: o que realmente chega à Sefin, por regra do Anexo VI (issue #29).

A biblioteca roda inteira (monta e assina a DPS); só o transporte HTTP é trocado pela Sefin
simulada. Cada teste confere a presença ou a ausência de `pAliq` no XML recebido.
"""

import datetime as dt
from decimal import Decimal

import pytest
from lxml import etree

from cadastros.models import Pessoa, Servico
from conftest import cnpj_de_teste
from fiscal.models import Nfse, ParametrosFiscais
from fiscal.services import emissao
from fiscal.services import nfse as servico_nfse
from fiscal.tests.apoio import criar_cadastros_de_teste

pytestmark = pytest.mark.django_db
S = Nfse.Situacao
R = ParametrosFiscais.RegimeTributario
NS = "{http://www.sped.fazenda.gov.br/nfse}"
COMPETENCIA = dt.date(2026, 10, 1)


def _parametros(**campos):
    parametros = ParametrosFiscais.obter()
    for campo, valor in campos.items():
        setattr(parametros, campo, valor)
    parametros.save()
    return parametros


def _convenio_do_emissor(*, ativacao=None, aderente=True):
    parametros = ParametrosFiscais.obter()
    parametros.convenio_resultado = {"aderente": aderente, "data_ativacao": ativacao}
    parametros.save()


def _servico(**campos):
    _, servico = criar_cadastros_de_teste()
    for campo, valor in campos.items():
        setattr(servico, campo, valor)
    servico.save()
    return servico


def _emitir(empresa, nota):
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    return nota


def _p_aliq(sefin):
    """Valor de `pAliq` na última DPS recebida pela Sefin; `None` se o campo não foi enviado."""
    campo = next(etree.fromstring(sefin.dps_recebidas[-1]).iter(NS + "pAliq"), None)
    return None if campo is None else campo.text


# -- prestador não optante --------------------------------------------------------------------


def test_e0617_nao_optante_em_municipio_conveniado_nao_envia_paliq(
    empresa_pronta, nova_nota, sefin
):
    """O defeito da issue: antes da correção este envio era rejeitado pela Sefin."""
    nota = _emitir(empresa_pronta, nova_nota())

    assert nota.situacao == S.AUTORIZADA
    assert _p_aliq(sefin) is None
    assert nota.complementos["aliquota_issqn"]["codigo_regra"] == "E0617"


def test_e0619_nao_optante_com_convenio_nao_ativo_na_competencia_envia_paliq(
    empresa_pronta, nova_nota, sefin
):
    _convenio_do_emissor(ativacao="2026-10-02")  # ativa depois da competência (2026-10-01)

    nota = _emitir(empresa_pronta, nova_nota())

    assert nota.situacao == S.AUTORIZADA
    assert _p_aliq(sefin) == "2.00"
    assert nota.complementos["aliquota_issqn"]["codigo_regra"] == "E0619"


def test_e0619_convenio_ativo_no_proprio_dia_da_competencia_ja_proibe(
    empresa_pronta, nova_nota, sefin
):
    _convenio_do_emissor(ativacao="2026-10-01")

    _emitir(empresa_pronta, nova_nota())

    assert _p_aliq(sefin) is None


def test_e0604_regime_especial_proibe_paliq_mesmo_sem_convenio(empresa_pronta, nova_nota, sefin):
    _parametros(regime_especial=6)
    _convenio_do_emissor(ativacao="2026-10-02")

    nota = _emitir(empresa_pronta, nova_nota())

    assert _p_aliq(sefin) is None
    assert nota.complementos["aliquota_issqn"]["codigo_regra"] == "E0604"


# -- MEI e ME/EPP -----------------------------------------------------------------------------


def test_e0600_mei_nunca_envia_paliq(empresa_pronta, nova_nota, sefin):
    _parametros(regime_tributario=R.MEI)
    _convenio_do_emissor(ativacao="2999-01-01")  # nem com convênio inativo

    nota = _emitir(empresa_pronta, nova_nota())

    assert _p_aliq(sefin) is None
    assert nota.complementos["aliquota_issqn"]["codigo_regra"] == "E0600"


def _simples(apuracao):
    _parametros(regime_tributario=R.SIMPLES_NACIONAL, regime_apuracao_simples=apuracao)


def test_e0625_simples_pelo_simples_sem_retencao_nao_envia_paliq(empresa_pronta, nova_nota, sefin):
    _simples(1)

    nota = _emitir(empresa_pronta, nova_nota())

    assert _p_aliq(sefin) is None
    assert nota.complementos["aliquota_issqn"]["codigo_regra"] == "E0625"


def test_e0621_simples_pelo_simples_com_retencao_envia_paliq(empresa_pronta, nova_nota, sefin):
    _simples(1)
    _servico(iss_retido=True)

    nota = _emitir(empresa_pronta, nova_nota())

    assert nota.situacao == S.AUTORIZADA
    assert _p_aliq(sefin) == "2.00"
    assert nota.complementos["aliquota_issqn"]["codigo_regra"] == "E0621"


def test_e0621_aliquota_abaixo_de_1_8_bloqueia_e_nada_chega_a_sefin(
    empresa_pronta, nova_nota, sefin
):
    _simples(1)
    _servico(iss_retido=True, aliquota_iss=Decimal("1.50"))
    nota = nova_nota()

    with pytest.raises(emissao.ErroDeEmissao, match="E0621"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    nota.refresh_from_db()
    assert nota.situacao == S.RASCUNHO and sefin.total_de_posts == 0


def test_e0621_aliquota_exatamente_1_8_passa(empresa_pronta, nova_nota, sefin):
    _simples(1)
    _servico(iss_retido=True, aliquota_iss=Decimal("1.80"))

    _emitir(empresa_pronta, nova_nota())

    assert _p_aliq(sefin) == "1.80"


def test_e0628_e0631_simples_com_convenio_nao_ativo(empresa_pronta, nova_nota, sefin):
    _simples(1)
    _convenio_do_emissor(ativacao="2026-10-02")

    nota_sem_retencao = _emitir(empresa_pronta, nova_nota())
    assert _p_aliq(sefin) is None
    assert nota_sem_retencao.complementos["aliquota_issqn"]["codigo_regra"] == "E0631"

    _servico(iss_retido=True)
    nota_retida = _emitir(empresa_pronta, nova_nota())
    assert _p_aliq(sefin) == "2.00"
    assert nota_retida.complementos["aliquota_issqn"]["codigo_regra"] == "E0628"


@pytest.mark.parametrize("apuracao", [2, 3])
def test_e0635_e0640_simples_com_issqn_fora_do_simples(apuracao, empresa_pronta, nova_nota, sefin):
    _simples(apuracao)

    ativo = _emitir(empresa_pronta, nova_nota())
    assert _p_aliq(sefin) is None
    assert ativo.complementos["aliquota_issqn"]["codigo_regra"] == "E0635"

    _convenio_do_emissor(ativacao="2026-10-02")
    inativo = _emitir(empresa_pronta, nova_nota())
    assert _p_aliq(sefin) == "2.00"
    assert inativo.complementos["aliquota_issqn"]["codigo_regra"] == "E0640"


def test_e0604_contra_e0640_e_conflito_e_nada_e_enviado(empresa_pronta, nova_nota, sefin):
    _simples(2)
    _parametros(regime_especial=6)
    _convenio_do_emissor(ativacao="2026-10-02")
    nota = nova_nota()

    with pytest.raises(emissao.ErroDeEmissao, match="E0604"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    assert sefin.total_de_posts == 0


# -- alíquota obrigatória sem valor -----------------------------------------------------------


def test_e0619_sem_aliquota_no_cadastro_do_servico_bloqueia(empresa_pronta, nova_nota, sefin):
    _convenio_do_emissor(ativacao="2026-10-02")
    _servico(aliquota_iss=None)
    nota = nova_nota()

    with pytest.raises(emissao.ErroDeEmissao, match="E0619"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    assert sefin.total_de_posts == 0


# -- município de incidência diferente do emissor ---------------------------------------------

TOMADOR_EM_OUTRO_MUNICIPIO = "3550308"


def _servico_de_mao_de_obra_com_tomador_de_fora():
    """Serviço 17.05.01 (ISSQN devido no município do tomador) e um tomador em outro município."""
    criar_cadastros_de_teste()
    tomador, _ = Pessoa.objects.get_or_create(
        documento=cnpj_de_teste("054239600001"),
        defaults={
            "tipo": Pessoa.Tipo.PESSOA_JURIDICA,
            "nome": "TOMADOR DE OUTRO MUNICIPIO LTDA",
            "logradouro": "Av. Paulista",
            "numero": "1000",
            "bairro": "Bela Vista",
            "codigo_municipio": TOMADOR_EM_OUTRO_MUNICIPIO,
            "cep": "01310100",
            "emails_envio": ["contas@tomador-sp.test"],
        },
    )
    servico, _ = Servico.objects.get_or_create(
        codigo_tributacao_nacional="170501",
        codigo_tributacao_municipal="002",
        defaults={
            "nome": "Mão de obra temporária",
            "descricao": "Fornecimento de mão de obra.",
            "aliquota_iss": Decimal("3.00"),
            "vigencia_inicio": dt.date(2026, 1, 1),
        },
    )
    return servico_nfse.criar_rascunho(
        {
            "tomador": tomador.pk,
            "servico": servico.pk,
            "competencia": COMPETENCIA,
            "valores": {"servico": "1000.00"},
        },
        usuario=None,
    )


def test_incidencia_no_municipio_do_tomador_consulta_o_convenio_dele(empresa_pronta, sefin):
    """O emissor tem convênio ativo, mas o ISSQN é devido onde o convênio não está ativo."""
    sefin.municipios_nao_aderentes.add(TOMADOR_EM_OUTRO_MUNICIPIO)
    nota = _servico_de_mao_de_obra_com_tomador_de_fora()

    nota = _emitir(empresa_pronta, nota)

    assert nota.situacao == S.AUTORIZADA
    assert _p_aliq(sefin) == "3.00"
    avaliacao = nota.complementos["aliquota_issqn"]
    assert avaliacao["codigo_regra"] == "E0619"
    assert avaliacao["municipio_incidencia"] == TOMADOR_EM_OUTRO_MUNICIPIO
    assert avaliacao["regra_incidencia"] == "ET"
    consultas = [
        c for c in sefin.chamadas if c[1].endswith(f"/{TOMADOR_EM_OUTRO_MUNICIPIO}/convenio")
    ]
    assert consultas


def test_incidencia_no_municipio_do_tomador_com_convenio_ativo_nao_envia(empresa_pronta, sefin):

    nota = _emitir(empresa_pronta, _servico_de_mao_de_obra_com_tomador_de_fora())

    assert _p_aliq(sefin) is None
    assert nota.complementos["aliquota_issqn"]["codigo_regra"] == "E0617"


def test_sem_conseguir_consultar_o_convenio_do_municipio_a_nota_volta_a_rascunho(
    empresa_pronta, sefin
):
    sefin.fora_do_ar = True
    nota = _servico_de_mao_de_obra_com_tomador_de_fora()

    emissao.solicitar_emissao(
        nota, usuario=None, empresa=empresa_pronta
    )  # a decisão fica p/ o envio
    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()

    assert nota.situacao == S.RASCUNHO and sefin.total_de_posts == 0
    assert "convênio ativo" in nota.mensagem


# -- prévia ------------------------------------------------------------------------------------


def test_a_previa_mostra_a_decisao_de_paliq_com_o_codigo_da_regra(empresa_pronta):
    tomador, servico = criar_cadastros_de_teste()

    preparo = servico_nfse.preparar(
        {
            "tomador": tomador.pk,
            "servico": servico.pk,
            "competencia": COMPETENCIA,
            "valores": {"servico": "1000.00"},
        }
    )

    decisao = preparo.complementos["aliquota_issqn"]
    assert decisao["envia"] is False and decisao["codigo_regra"] == "E0617"
    assert decisao["municipio_incidencia"] == "2903201" and decisao["regra_incidencia"] == "EP"
    assert "convênio" in decisao["explicacao"]
