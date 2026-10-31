"""Dispatcher dos agendamentos: data e competência certas, falha que não conta, suspensão e atraso.

O relógio é sempre injetado (`agora`); nada depende do dia em que o teste roda. Sem rede: o e-mail
só vira registro na fila.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model

from agendamentos.models import Agendamento, ExecucaoAgendamento
from agendamentos.services import agenda
from agendamentos.tests.apoio import criar_agendamento, criar_modelo, criar_usuario, utc
from core.models import VinculoUsuarioEmpresa
from core.permissoes import Perfil
from documentos.models import EnvioEmail
from documentos.tests.apoio import configurar_email
from fiscal.models import Nfse

pytestmark = pytest.mark.django_db
A, E = Agendamento.Situacao, ExecucaoAgendamento.Situacao
CRIACAO = utc("2026-11-01T12:00")


@pytest.fixture
def responsavel(empresa_pronta):
    return criar_usuario("resp@exemplo.test", empresa_pronta)


@pytest.fixture
def admin(empresa_pronta):
    return criar_usuario("admin@exemplo.test", empresa_pronta, Perfil.ADMINISTRADOR)


@pytest.fixture
def modelo(empresa_pronta):
    return criar_modelo()


@pytest.fixture
def rodar(empresa_pronta):
    """`rodar(agora)`: uma passada do dispatcher na empresa ativa."""
    return lambda agora: agenda.despachar(agora, empresa=empresa_pronta)


def gerados(totais):
    return totais[agenda.GERADA]


# -- na data certa, com a competência certa --------------------------------------------------


def test_gera_o_rascunho_na_data_e_hora_do_agendamento_e_nao_antes(modelo, responsavel, rodar):
    agendamento = criar_agendamento(modelo, responsavel, agora=CRIACAO)
    assert agendamento.proxima_execucao == utc("2026-11-05T11:00")  # 08:00 de Brasília

    antes = rodar(utc("2026-11-05T10:59"))
    assert gerados(antes) == 0 and Nfse.objects.count() == 0

    depois = rodar(utc("2026-11-05T11:00"))

    assert gerados(depois) == 1
    nota = Nfse.objects.get()
    assert nota.situacao == Nfse.Situacao.RASCUNHO
    assert nota.competencia == dt.date(2026, 11, 1)  # mês da execução
    assert nota.criado_por_email == "resp@exemplo.test"
    agendamento.refresh_from_db()
    assert agendamento.execucoes_realizadas == 1 and agendamento.situacao == A.ATIVO
    assert agendamento.proxima_execucao == utc("2026-12-05T11:00")
    execucao = agendamento.execucoes.get()
    assert (execucao.data_execucao, execucao.situacao, execucao.nfse) == (
        dt.date(2026, 11, 5), E.GERADA, nota,
    )  # fmt: skip


def test_a_competencia_acompanha_o_mes_de_cada_execucao(modelo, responsavel, rodar):
    criar_agendamento(modelo, responsavel, agora=CRIACAO)

    rodar(utc("2026-11-05T11:00"))
    rodar(utc("2026-12-05T11:00"))

    assert sorted(Nfse.objects.values_list("competencia", flat=True)) == [
        dt.date(2026, 11, 1), dt.date(2026, 12, 1),
    ]  # fmt: skip


def test_na_virada_do_dia_em_utc_vale_a_data_de_brasilia(modelo, responsavel, rodar):
    # 23:30 de Brasília de 31/10 = 02:30 UTC de 01/11. A competência é OUTUBRO.
    agendamento = criar_agendamento(
        modelo, responsavel, agora=utc("2026-10-31T12:00"), nome="Noturno", frequencia="diaria",
        dia_do_mes=None, hora=dt.time(23, 30), data_inicio=dt.date(2026, 10, 31),
    )  # fmt: skip
    assert agendamento.proxima_execucao == utc("2026-11-01T02:30")

    assert gerados(rodar(utc("2026-11-01T02:20"))) == 0  # 23:20 em Brasília: ainda não
    assert gerados(rodar(utc("2026-11-01T02:35"))) == 1

    assert Nfse.objects.get().competencia == dt.date(2026, 10, 1)
    assert agendamento.execucoes.get().data_execucao == dt.date(2026, 10, 31)


def test_feriado_e_fim_de_semana_executam(modelo, responsavel, rodar):
    criar_agendamento(
        modelo, responsavel, agora=utc("2026-12-23T12:00"), frequencia="diaria", dia_do_mes=None,
        data_inicio=dt.date(2026, 12, 24),
    )  # fmt: skip

    # 24/12 (quinta), 25/12 (sexta, Natal), 26/12 (sábado) e 27/12 (domingo)
    totais = [gerados(rodar(utc(f"2026-12-{dia}T11:01"))) for dia in (24, 25, 26, 27)]

    assert totais == [1, 1, 1, 1] and Nfse.objects.count() == 4


# -- fim da série ----------------------------------------------------------------------------


def test_limite_de_execucoes_encerra_o_agendamento(modelo, responsavel, rodar):
    agendamento = criar_agendamento(
        modelo, responsavel, agora=CRIACAO, frequencia="diaria", dia_do_mes=None,
        data_inicio=dt.date(2026, 11, 2), max_execucoes=2,
    )  # fmt: skip

    rodar(utc("2026-11-02T11:01"))
    agendamento.refresh_from_db()
    assert agendamento.situacao == A.ATIVO
    rodar(utc("2026-11-03T11:01"))
    agendamento.refresh_from_db()

    assert agendamento.situacao == A.ENCERRADO and agendamento.proxima_execucao is None
    assert "2 execuções" in agendamento.motivo_situacao
    assert gerados(rodar(utc("2026-11-04T11:01"))) == 0 and Nfse.objects.count() == 2


def test_data_de_fim_encerra_depois_da_ultima_data(modelo, responsavel, rodar):
    agendamento = criar_agendamento(
        modelo, responsavel, agora=CRIACAO, frequencia="diaria", dia_do_mes=None,
        data_inicio=dt.date(2026, 11, 2), data_fim=dt.date(2026, 11, 3),
    )  # fmt: skip

    rodar(utc("2026-11-02T11:01"))
    rodar(utc("2026-11-03T11:01"))

    agendamento.refresh_from_db()
    assert agendamento.situacao == A.ENCERRADO and Nfse.objects.count() == 2
    assert "data de fim" in agendamento.motivo_situacao


def test_execucao_unica_gera_uma_vez_e_encerra(modelo, responsavel, rodar):
    agendamento = criar_agendamento(
        modelo, responsavel, agora=CRIACAO, frequencia="unica", dia_do_mes=None,
        data_inicio=dt.date(2026, 11, 10),
    )  # fmt: skip

    assert gerados(rodar(utc("2026-11-10T11:01"))) == 1

    agendamento.refresh_from_db()
    assert agendamento.situacao == A.ENCERRADO and "única" in agendamento.motivo_situacao


# -- falha não conta como execução -----------------------------------------------------------


def test_falha_ao_gerar_registra_notifica_e_nao_conta_a_execucao(modelo, responsavel, admin, rodar):
    configurar_email("smtp")
    modelo.servico.vigencia_fim = dt.date(2026, 10, 31)  # sem vigência em novembro
    modelo.servico.save()
    agendamento = criar_agendamento(modelo, responsavel, agora=CRIACAO, max_execucoes=1)

    totais = rodar(utc("2026-11-05T11:01"))

    assert totais[agenda.FALHOU] == 1 and Nfse.objects.count() == 0
    agendamento.refresh_from_db()
    assert agendamento.execucoes_realizadas == 0  # a falha não conta
    assert agendamento.situacao == A.ATIVO
    assert agendamento.proxima_execucao == utc("2026-12-05T11:00")  # tenta na próxima data
    execucao = agendamento.execucoes.get()
    assert execucao.situacao == E.FALHOU and "não tem versão vigente em 11/2026" in execucao.erro
    aviso = EnvioEmail.objects.get(tipo=EnvioEmail.Tipo.AVISO_AGENDAMENTO)
    assert set(aviso.destinatarios) == {"resp@exemplo.test", "admin@exemplo.test"}
    assert "não conseguiu gerar" in aviso.assunto and "versão vigente" in aviso.corpo_avulso


def test_depois_de_corrigir_a_proxima_data_gera_e_so_entao_conta(modelo, responsavel, rodar):
    modelo.servico.vigencia_fim = dt.date(2026, 10, 31)
    modelo.servico.save()
    agendamento = criar_agendamento(modelo, responsavel, agora=CRIACAO, max_execucoes=1)
    rodar(utc("2026-11-05T11:01"))  # falha
    modelo.servico.vigencia_fim = None  # corrigido a tempo da próxima data
    modelo.servico.save()

    rodar(utc("2026-12-05T11:01"))

    agendamento.refresh_from_db()
    assert agendamento.execucoes_realizadas == 1 and agendamento.situacao == A.ENCERRADO
    assert list(agendamento.execucoes.values_list("situacao", flat=True)) == [E.GERADA, E.FALHOU]


def test_modelo_desativado_depois_de_agendar_falha_na_execucao(modelo, responsavel, rodar):
    agendamento = criar_agendamento(
        modelo, responsavel, agora=CRIACAO, frequencia="unica", dia_do_mes=None,
        data_inicio=dt.date(2026, 11, 10),
    )  # fmt: skip
    modelo.ativo = False
    modelo.save()

    totais = rodar(utc("2026-11-10T11:01"))

    assert totais[agenda.FALHOU] == 1
    agendamento.refresh_from_db()
    assert agendamento.situacao == A.ENCERRADO and "inativo" in agendamento.motivo_situacao
    assert agendamento.execucoes_realizadas == 0


# -- responsável sem acesso suspende e avisa o administrador ------------------------------------


def _desativar_vinculo(responsavel, empresa):
    VinculoUsuarioEmpresa.objects.filter(usuario=responsavel, empresa=empresa).update(ativo=False)


def _sem_permissao(responsavel, empresa):
    VinculoUsuarioEmpresa.objects.filter(usuario=responsavel, empresa=empresa).update(
        perfil=Perfil.CONSULTA
    )


def _usuario_desativado(responsavel, empresa):
    get_user_model().objects.filter(pk=responsavel.pk).update(is_active=False)


@pytest.mark.parametrize(
    ("quebrar", "trecho"),
    [
        (_desativar_vinculo, "não tem mais vínculo ativo"),
        (_sem_permissao, "não tem mais permissão para emitir notas"),
        (_usuario_desativado, "está desativado"),
    ],
)
def test_responsavel_sem_acesso_suspende_o_agendamento_e_avisa_o_administrador(
    modelo, responsavel, admin, rodar, empresa_pronta, quebrar, trecho
):
    configurar_email("smtp")
    agendamento = criar_agendamento(modelo, responsavel, agora=CRIACAO)
    quebrar(responsavel, empresa_pronta)

    totais = rodar(utc("2026-11-05T11:01"))

    assert totais[agenda.SUSPENSA] == 1 and Nfse.objects.count() == 0
    agendamento.refresh_from_db()
    assert agendamento.situacao == A.SUSPENSO and agendamento.proxima_execucao is None
    assert trecho in agendamento.motivo_situacao
    execucao = agendamento.execucoes.get()
    assert execucao.situacao == E.SUSPENSA and trecho in execucao.erro
    aviso = EnvioEmail.objects.get(tipo=EnvioEmail.Tipo.AVISO_AGENDAMENTO)
    assert aviso.destinatarios == ["admin@exemplo.test"]
    assert "SUSPENSO" in aviso.corpo_avulso and trecho in aviso.corpo_avulso
    assert gerados(rodar(utc("2026-12-05T11:01"))) == 0  # suspenso não gera mais nada


def test_sem_email_configurado_o_historico_fica_e_nenhum_email_e_criado(
    modelo, responsavel, admin, rodar, empresa_pronta
):
    agendamento = criar_agendamento(modelo, responsavel, agora=CRIACAO)
    _desativar_vinculo(responsavel, empresa_pronta)

    rodar(utc("2026-11-05T11:01"))

    assert EnvioEmail.objects.count() == 0
    assert agendamento.execucoes.get().situacao == E.SUSPENSA


def test_o_master_pode_ser_o_responsavel_e_o_rascunho_sai_no_nome_dele(
    modelo, rodar, empresa_pronta
):
    from conftest import criar_usuario_de_teste

    master = criar_usuario_de_teste("master@exemplo.test", master=True)
    agendamento = criar_agendamento(modelo, master, agora=CRIACAO)

    assert gerados(rodar(utc("2026-11-05T11:01"))) == 1
    assert Nfse.objects.get().criado_por_email == "master@exemplo.test"
    assert agendamento.responsavel_email == "master@exemplo.test"


# -- idempotência sequencial -----------------------------------------------------------------


def test_rodar_duas_vezes_na_mesma_hora_gera_um_rascunho(modelo, responsavel, rodar):
    criar_agendamento(modelo, responsavel, agora=CRIACAO)

    primeira = rodar(utc("2026-11-05T11:01"))
    segunda = rodar(utc("2026-11-05T11:01"))

    assert gerados(primeira) == 1 and gerados(segunda) == 0
    assert Nfse.objects.count() == 1 and ExecucaoAgendamento.objects.count() == 1


def test_mudar_a_hora_depois_da_execucao_do_dia_nao_gera_um_segundo_rascunho(
    modelo, responsavel, rodar, empresa_pronta
):
    agendamento = criar_agendamento(
        modelo, responsavel, agora=CRIACAO, frequencia="diaria", dia_do_mes=None,
        data_inicio=dt.date(2026, 11, 2),
    )  # fmt: skip
    rodar(utc("2026-11-02T11:01"))  # executou o dia 02 às 08:01
    agendamento.refresh_from_db()

    # às 09:00 alguém muda a hora para 10:00: "hoje às 10:00" voltaria a ser futuro
    agenda.salvar(
        {"hora": dt.time(10, 0)}, agendamento=agendamento, usuario=responsavel,
        empresa=empresa_pronta, agora=utc("2026-11-02T12:00"),
    )  # fmt: skip
    agendamento.refresh_from_db()
    assert agendamento.proxima_execucao == utc("2026-11-02T13:00")

    totais = rodar(utc("2026-11-02T13:01"))

    assert totais[agenda.JA_EXECUTADA] == 1 and gerados(totais) == 0
    assert Nfse.objects.count() == 1  # a data 02/11 já tinha o seu rascunho
    agendamento.refresh_from_db()
    assert agendamento.execucoes_realizadas == 1
    assert agendamento.proxima_execucao == utc("2026-11-03T13:00")


# -- sistema fora do ar: tolerância e datas perdidas --------------------------------------------


def test_data_muito_atrasada_vira_aviso_e_so_a_mais_recente_gera(modelo, responsavel, admin, rodar):
    configurar_email("smtp")
    agendamento = criar_agendamento(
        modelo, responsavel, agora=CRIACAO, frequencia="diaria", dia_do_mes=None,
        data_inicio=dt.date(2026, 11, 2),
    )  # fmt: skip
    assert agendamento.proxima_execucao == utc("2026-11-02T11:00")

    # o sistema ficou parado: 05/11 às 09:00 (Brasília). 02, 03 e 04 passaram da tolerância (12 h)
    totais = rodar(utc("2026-11-05T12:00"))

    assert totais[agenda.PERDIDA] == 1 and gerados(totais) == 1
    assert Nfse.objects.count() == 1  # nada de rascunhos em massa
    perdida = agendamento.execucoes.get(situacao=E.PERDIDA)
    assert perdida.data_execucao == dt.date(2026, 11, 2)
    assert "3 data(s)" in perdida.erro and "não contam como execução" in perdida.erro
    assert agendamento.execucoes.get(situacao=E.GERADA).data_execucao == dt.date(2026, 11, 5)
    agendamento.refresh_from_db()
    assert agendamento.execucoes_realizadas == 1
    assert agendamento.proxima_execucao == utc("2026-11-06T11:00")
    assert EnvioEmail.objects.filter(assunto__contains="data não executada").exists()


def test_atraso_dentro_da_tolerancia_ainda_executa(modelo, responsavel, rodar):
    criar_agendamento(modelo, responsavel, agora=CRIACAO)

    totais = rodar(utc("2026-11-05T22:00"))  # 11 h depois das 08:00 de Brasília

    assert gerados(totais) == 1 and totais[agenda.PERDIDA] == 0


def test_a_tolerancia_nunca_passa_de_um_dia(settings):
    settings.FREENFSE_AGENDAMENTO_TOLERANCIA_HORAS = 72

    assert agenda.tolerancia() == dt.timedelta(hours=23)


# -- reativar e editar: nada retroativo ------------------------------------------------------


def test_reativar_vale_so_a_proxima_data_futura_sem_disparo_retroativo(
    modelo, responsavel, rodar, empresa_pronta
):
    agendamento = criar_agendamento(
        modelo, responsavel, agora=CRIACAO, frequencia="diaria", dia_do_mes=None,
        data_inicio=dt.date(2026, 11, 2),
    )  # fmt: skip
    agenda.suspender(agendamento, usuario=responsavel, empresa=empresa_pronta)
    assert agendamento.proxima_execucao is None

    agenda.reativar(
        agendamento, usuario=responsavel, empresa=empresa_pronta, agora=utc("2026-11-13T12:00")
    )

    assert agendamento.situacao == A.ATIVO
    assert agendamento.proxima_execucao == utc("2026-11-14T11:00")  # 11 dias parado: nada atrasado
    assert gerados(rodar(utc("2026-11-13T12:30"))) == 0
    assert ExecucaoAgendamento.objects.count() == 0 and Nfse.objects.count() == 0


def test_so_se_reativa_quem_esta_suspenso_e_com_responsavel_valido(
    modelo, responsavel, rodar, empresa_pronta
):
    agendamento = criar_agendamento(modelo, responsavel, agora=CRIACAO)
    with pytest.raises(agenda.ErroDeAgendamento, match="suspenso"):
        agenda.reativar(agendamento, usuario=responsavel, empresa=empresa_pronta, agora=CRIACAO)

    agenda.suspender(agendamento, usuario=responsavel, empresa=empresa_pronta)
    _desativar_vinculo(responsavel, empresa_pronta)
    with pytest.raises(agenda.ErroDeAgendamento) as erro:
        agenda.reativar(agendamento, usuario=responsavel, empresa=empresa_pronta, agora=CRIACAO)
    assert "vínculo ativo" in erro.value.erros["responsavel"]


def test_trocar_a_regra_recalcula_a_partir_de_agora_mas_renomear_nao(
    modelo, responsavel, empresa_pronta
):
    agendamento = criar_agendamento(modelo, responsavel, agora=CRIACAO)
    antes = agendamento.proxima_execucao  # 05/11

    agenda.salvar(
        {"nome": "Outro nome"}, agendamento=agendamento, usuario=responsavel,
        empresa=empresa_pronta, agora=utc("2026-11-10T12:00"),
    )  # fmt: skip
    assert agendamento.proxima_execucao == antes  # data vencida continua pendente de execução

    agenda.salvar(
        {"dia_do_mes": 20}, agendamento=agendamento, usuario=responsavel, empresa=empresa_pronta,
        agora=utc("2026-11-10T12:00"),
    )  # fmt: skip
    assert agendamento.proxima_execucao == utc("2026-11-20T11:00")


# -- regras ao salvar ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campos", "campo"),
    [
        ({"data_inicio": dt.date(2026, 10, 1)}, "data_inicio"),
        ({"data_fim": dt.date(2027, 1, 1), "max_execucoes": 3}, "max_execucoes"),
        ({"dia_do_mes": 32}, "dia_do_mes"),
        ({"nome": ""}, "nome"),
    ],
)
def test_agendamento_invalido_aponta_o_campo(modelo, responsavel, campos, campo):
    with pytest.raises(agenda.ErroDeAgendamento) as erro:
        criar_agendamento(modelo, responsavel, agora=CRIACAO, **campos)

    assert campo in erro.value.erros


def test_nome_repetido_modelo_inativo_e_responsavel_sem_permissao_sao_recusados(
    modelo, responsavel, empresa_pronta
):
    criar_agendamento(modelo, responsavel, agora=CRIACAO, nome="Cobrança")
    with pytest.raises(agenda.ErroDeAgendamento) as repetido:
        criar_agendamento(modelo, responsavel, agora=CRIACAO, nome="COBRANÇA")
    assert "Já existe" in repetido.value.erros["nome"]

    inativo = criar_modelo(nome="Parado", ativo=False)
    with pytest.raises(agenda.ErroDeAgendamento) as modelo_inativo:
        criar_agendamento(inativo, responsavel, agora=CRIACAO, nome="Outro")
    assert "inativo" in modelo_inativo.value.erros["modelo"]

    consulta = criar_usuario("consulta@exemplo.test", empresa_pronta, Perfil.CONSULTA)
    with pytest.raises(agenda.ErroDeAgendamento) as sem_permissao:
        criar_agendamento(modelo, consulta, agora=CRIACAO, nome="Terceiro")
    assert "permissão para emitir" in sem_permissao.value.erros["responsavel"]


def test_agendamento_sem_nenhuma_data_futura_e_recusado(modelo, responsavel):
    with pytest.raises(agenda.ErroDeAgendamento) as erro:
        criar_agendamento(
            modelo, responsavel, agora=CRIACAO, frequencia="unica", dia_do_mes=None,
            data_inicio=dt.date(2026, 11, 1), hora=dt.time(8, 0),
        )  # fmt: skip

    assert "nenhuma execução futura" in erro.value.erros["geral"]
