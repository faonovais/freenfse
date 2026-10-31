"""Modelos de NFS-e: rascunho por cópia (snapshot), versão do serviço, validação e e-mail."""

import datetime as dt
from decimal import Decimal

import pytest

from agendamentos.models import ModeloNfse, OrigemNfse
from agendamentos.services import modelos
from agendamentos.tests.apoio import criar_modelo, criar_usuario
from cadastros.models import Pessoa, Servico
from documentos.models import ConfiguracaoEmail
from documentos.services import envio_email
from fiscal.models import Nfse
from fiscal.services import emissao
from fiscal.services.nfse import ErroDeNota

pytestmark = pytest.mark.django_db
EXECUCAO = dt.date(2026, 11, 5)


@pytest.fixture
def responsavel(empresa_pronta):
    return criar_usuario("resp@exemplo.test", empresa_pronta)


def emitir(empresa, nota, usuario=None):
    emissao.solicitar_emissao(nota, usuario=usuario, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    return nota


# -- o rascunho é uma cópia ----------------------------------------------------------------


def test_o_rascunho_copia_tomador_servico_valores_e_texto_do_modelo(empresa_pronta, responsavel):
    modelo = criar_modelo()

    nota = modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)

    assert nota.situacao == Nfse.Situacao.RASCUNHO
    assert nota.competencia == dt.date(2026, 11, 1)  # mês da execução
    assert nota.tomador_nome == "TOMADOR FICTICIO LTDA"
    assert nota.valor_servico == Decimal("1500.00")
    assert nota.complementos["informacoes_complementares"] == "Referente a 11/2026."
    assert nota.servico["nome"] == "Consultoria"
    assert nota.criado_por_email == "resp@exemplo.test"
    origem = OrigemNfse.objects.get(nfse=nota)
    assert origem.modelo == modelo and origem.modelo_nome == modelo.nome


def test_competencia_do_mes_anterior(empresa_pronta, responsavel):
    modelo = criar_modelo(competencia_padrao=ModeloNfse.Competencia.MES_ANTERIOR)

    nota = modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=dt.date(2027, 1, 5))

    assert nota.competencia == dt.date(2026, 12, 1)  # virada do ano
    assert nota.complementos["informacoes_complementares"] == "Referente a 12/2026."


def test_alterar_o_modelo_depois_da_emissao_nao_muda_a_nota_emitida(
    empresa_pronta, responsavel, sefin
):
    modelo = criar_modelo(email_assunto_modelo="NFS-e {numero_nfse} do modelo")
    nota = modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)
    nota = emitir(empresa_pronta, nota, responsavel)
    assert nota.situacao == Nfse.Situacao.AUTORIZADA
    antes = (nota.valores, nota.complementos, nota.tomador, nota.servico, nota.hash_xml_nfse)
    sobreposicao_antes = envio_email.configuracao_efetiva(ConfiguracaoEmail.obter(), nota)

    modelo.valores = {"servico": "9999.00"}
    modelo.complementos = {"informacoes_complementares": "Texto novo"}
    modelo.email_assunto_modelo = "Assunto totalmente diferente"
    modelo.nome = "Renomeado"
    modelo.save()
    modelo.tomador.nome = "TOMADOR RENOMEADO"
    modelo.tomador.save()
    nota.refresh_from_db()

    assert (
        nota.valores,
        nota.complementos,
        nota.tomador,
        nota.servico,
        nota.hash_xml_nfse,
    ) == antes
    assert nota.valor_servico == Decimal("1500.00")
    assert envio_email.configuracao_efetiva(ConfiguracaoEmail.obter(), nota) == sobreposicao_antes
    assert OrigemNfse.objects.get(nfse=nota).modelo_nome == "Mensalidade de consultoria"


def test_alterar_o_modelo_nao_muda_um_rascunho_ja_criado_so_os_proximos(
    empresa_pronta, responsavel
):
    modelo = criar_modelo()
    primeiro = modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)

    modelo.valores = {"servico": "2000.00"}
    modelo.save()
    segundo = modelos.gerar_rascunho(
        modelo, usuario=responsavel, data_execucao=dt.date(2026, 12, 5)
    )

    primeiro.refresh_from_db()
    assert primeiro.valor_servico == Decimal("1500.00")
    assert segundo.valor_servico == Decimal("2000.00")


# -- versão vigente do serviço -------------------------------------------------------------


def test_usa_a_versao_do_servico_vigente_na_competencia(empresa_pronta, responsavel):
    modelo = criar_modelo()
    antiga = modelo.servico
    antiga.vigencia_fim = dt.date(2026, 11, 30)
    antiga.save()
    nova = Servico.objects.create(
        nome="Consultoria (2027)",
        descricao=antiga.descricao,
        codigo_tributacao_nacional=antiga.codigo_tributacao_nacional,
        codigo_tributacao_municipal=antiga.codigo_tributacao_municipal,
        aliquota_iss=Decimal("3.00"),
        vigencia_inicio=dt.date(2026, 12, 1),
    )

    em_novembro = modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)
    em_dezembro = modelos.gerar_rascunho(
        modelo, usuario=responsavel, data_execucao=dt.date(2026, 12, 5)
    )

    assert em_novembro.servico["id"] == antiga.pk
    assert em_dezembro.servico["id"] == nova.pk
    assert em_dezembro.servico["aliquota_iss"] == "3.00"


# -- falhas ao gerar (viram falha de execução no agendamento) -------------------------------


def test_servico_sem_vigencia_na_competencia_explica_o_que_fazer(empresa_pronta, responsavel):
    modelo = criar_modelo()
    modelo.servico.vigencia_fim = dt.date(2026, 10, 31)
    modelo.servico.save()

    with pytest.raises(ErroDeNota) as erro:
        modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)

    assert "não tem versão vigente em 11/2026" in erro.value.erros["servico"]
    assert Nfse.objects.count() == 0 and OrigemNfse.objects.count() == 0


def test_tomador_inativo_removido_ou_modelo_inativo_nao_geram(empresa_pronta, responsavel):
    modelo = criar_modelo()
    modelo.tomador.ativo = False
    modelo.tomador.save()
    with pytest.raises(ErroDeNota) as inativo:
        modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)
    assert "tomador ativo" in inativo.value.erros["tomador"]

    Pessoa.objects.filter(pk=modelo.tomador_id).delete()
    modelo.refresh_from_db()
    with pytest.raises(ErroDeNota) as removido:
        modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)
    assert "não existe mais" in removido.value.erros["tomador"]

    modelo.ativo = False
    with pytest.raises(ErroDeNota) as desligado:
        modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)
    assert "inativo" in desligado.value.erros["modelo"]
    assert Nfse.objects.count() == 0


def test_ibs_cbs_nao_e_do_modelo_o_rascunho_nunca_leva_o_grupo(empresa_pronta, responsavel):
    modelo = criar_modelo(
        complementos={
            "informacoes_complementares": "x",
            "ibs_cbs": {"codigo_indicador_operacao": "000001", "indicador_destinatario": 0},
        }
    )

    dados = modelos.dados_do_rascunho(modelo, data_execucao=EXECUCAO)
    nota = modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)

    assert "ibs_cbs" not in dados
    assert nota.complementos["ibs_cbs"] is None


# -- validação do modelo -------------------------------------------------------------------


def test_modelo_ativo_valido_nao_tem_erros(empresa_pronta):
    assert modelos.validar_modelo(criar_modelo(), hoje=EXECUCAO) == {}


@pytest.mark.parametrize(
    ("campos", "campo"),
    [
        (
            {"complementos": {"informacoes_complementares": "Ref. {xpto}"}},
            "informacoes_complementares",
        ),
        (
            {"complementos": {"informacoes_complementares": "Ref. {competencia"}},
            "informacoes_complementares",
        ),
        (
            {"complementos": {"informacoes_complementares": "x" * 2001}},
            "informacoes_complementares",
        ),
        ({"email_assunto_modelo": "NFS-e {desconhecida}"}, "email_assunto_modelo"),
        ({"email_corpo_modelo": "Olá {nome_tomador"}, "email_corpo_modelo"),
        ({"email_copias_fixas": ["isto-nao-e-email"]}, "email_copias_fixas"),
        ({"nome": "   "}, "nome"),
        ({"valores": {"servico": "0"}}, "valores.servico"),
        ({"valores": {}}, "valores.servico"),
    ],
)
def test_modelo_invalido_aponta_o_campo(empresa_pronta, campos, campo):
    modelo = criar_modelo(**campos)

    assert campo in modelos.validar_modelo(modelo, hoje=EXECUCAO)


def test_modelo_inativo_pode_ficar_incompleto(empresa_pronta):
    rascunho_de_modelo = criar_modelo(ativo=False, tomador=None, servico=None, valores={})

    assert modelos.validar_modelo(rascunho_de_modelo, hoje=EXECUCAO) == {}


def test_nome_do_modelo_e_unico_sem_diferenciar_maiusculas(empresa_pronta):
    from django.db import IntegrityError, transaction

    criar_modelo(nome="Mensalidade")

    with pytest.raises(IntegrityError), transaction.atomic():
        criar_modelo(nome="MENSALIDADE")


# -- sobreposição de e-mail por modelo (D21) -----------------------------------------------


def test_o_modelo_sobrepoe_so_o_que_define_e_herda_o_resto_da_empresa(empresa_pronta, responsavel):
    configuracao = ConfiguracaoEmail.obter()
    configuracao.anexar_pdf, configuracao.anexar_xml = True, True
    configuracao.envio_automatico = False
    configuracao.copias_fixas = ["financeiro@empresa.test"]
    configuracao.save()
    modelo = criar_modelo(
        email_anexar_pdf=False,
        email_envio_automatico=True,
        email_assunto_modelo="NFS-e {numero_nfse} — mensalidade",
        email_copias_fixas=[],
    )
    do_modelo = modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=EXECUCAO)
    avulsa = Nfse.objects.create(
        ambiente="producao_restrita", serie=900, competencia=EXECUCAO, valor_servico=Decimal("1")
    )

    efetiva = envio_email.configuracao_efetiva(configuracao, do_modelo)
    herdada = envio_email.configuracao_efetiva(configuracao, avulsa)

    assert efetiva["anexar_pdf"] is False
    assert efetiva["anexar_xml"] is True  # herdado
    assert efetiva["envio_automatico"] is True
    assert efetiva["assunto_modelo"] == "NFS-e {numero_nfse} — mensalidade"
    assert efetiva["corpo_modelo"] == configuracao.corpo_modelo  # herdado
    assert efetiva["copias_fixas"] == []  # lista vazia no modelo = sem cópias
    assert herdada["anexar_pdf"] is True and herdada["copias_fixas"] == ["financeiro@empresa.test"]


def test_modelo_sem_sobreposicao_deixa_tudo_para_a_empresa(empresa_pronta, responsavel):
    nota = modelos.gerar_rascunho(criar_modelo(), usuario=responsavel, data_execucao=EXECUCAO)

    assert OrigemNfse.objects.get(nfse=nota).email == {}
    configuracao = ConfiguracaoEmail.obter()
    assert (
        envio_email.configuracao_efetiva(configuracao, nota)["anexar_pdf"]
        == configuracao.anexar_pdf
    )
