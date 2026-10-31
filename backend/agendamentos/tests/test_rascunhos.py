"""Rascunhos: aprovação em lote pelo fluxo de emissão da Fase 3, descarte e alerta diário."""

import datetime as dt

import pytest

from agendamentos.models import OrigemNfse
from agendamentos.services import agenda, modelos, rascunhos
from agendamentos.tests.apoio import criar_agendamento, criar_modelo, criar_usuario, utc
from core.models import LogAuditoria
from core.permissoes import Perfil
from documentos.models import EnvioEmail
from documentos.tests.apoio import configurar_email
from fiscal.models import Nfse
from fiscal.services import emissao

pytestmark = pytest.mark.django_db
S = Nfse.Situacao
EXECUCAO = dt.date(2026, 11, 5)


@pytest.fixture
def emissor(empresa_pronta):
    return criar_usuario("emissor@exemplo.test", empresa_pronta)


@pytest.fixture
def modelo(empresa_pronta):
    return criar_modelo()


def tres_rascunhos(modelo, emissor):
    return [
        modelos.gerar_rascunho(modelo, usuario=emissor, data_execucao=dt.date(2026, 11, dia))
        for dia in (3, 4, 5)
    ]


def aprovar(ids, emissor, empresa, permissoes=("nfse.emitir",)):
    return rascunhos.aprovar_em_lote(
        ids, usuario=emissor, empresa=empresa, permissoes=set(permissoes)
    )


def emitir_a_fila(empresa, fila):
    """Executa as emissões enfileiradas (a tarefa Celery faz isto na vida real)."""
    for _schema, nfse_id in fila.emissoes:
        emissao.executar_emissao(empresa, nfse_id)


# -- aprovação em lote ---------------------------------------------------------------------


def test_aprovar_em_lote_emite_pelo_fluxo_da_fase_3_com_resultado_por_item(
    empresa_pronta, modelo, emissor, sefin, fila
):
    notas = tres_rascunhos(modelo, emissor)
    sefin.proximas("ok", ("rejeitar", [("E0188", "CNPJ inválido.")]), "ok")

    resultados = aprovar([n.pk for n in notas], emissor, empresa_pronta)

    assert [r["ok"] for r in resultados] == [True, True, True]  # todos entraram na fila
    assert {Nfse.objects.get(pk=n.pk).situacao for n in notas} == {S.ENVIANDO}
    fila.emissoes.extend(("schema", n.pk) for n in notas)
    emitir_a_fila(empresa_pronta, fila)
    situacoes = [Nfse.objects.get(pk=n.pk).situacao for n in notas]
    assert situacoes == [S.AUTORIZADA, S.REJEITADA, S.AUTORIZADA]  # a rejeição não parou o lote
    assert sefin.total_de_posts == 3
    assert LogAuditoria.objects.filter(acao="nfse_lote_aprovado").exists()


def test_o_lote_nao_para_numa_recusa_e_explica_cada_item(empresa_pronta, modelo, emissor):
    boa, outra = tres_rascunhos(modelo, emissor)[:2]
    ja_enviada = Nfse.objects.get(pk=outra.pk)
    ja_enviada.__dict__["_transicao_autorizada"] = True
    Nfse.objects.filter(pk=outra.pk).update(situacao=S.AUTORIZADA)

    resultados = aprovar([boa.pk, outra.pk, 999999], emissor, empresa_pronta)

    assert [(r["id"], r["ok"]) for r in resultados] == [
        (boa.pk, True),
        (outra.pk, False),
        (999999, False),
    ]
    assert resultados[1]["codigo"] == "nao_e_rascunho" and "autorizada" in resultados[1]["mensagem"]
    assert resultados[2]["codigo"] == "nao_encontrada"


def test_empresa_nao_pronta_recusa_todos_com_o_motivo(empresa_pronta, modelo, emissor):
    from fiscal.models import Certificado

    notas = tres_rascunhos(modelo, emissor)
    Certificado.objects.all().delete()

    resultados = aprovar([n.pk for n in notas], emissor, empresa_pronta)

    assert all(not r["ok"] and r["codigo"] == "empresa_nao_pronta" for r in resultados)
    assert {Nfse.objects.get(pk=n.pk).situacao for n in notas} == {S.RASCUNHO}


def test_nota_substituta_no_lote_exige_a_permissao_de_substituir(empresa_pronta, modelo, emissor):
    (nota,) = tres_rascunhos(modelo, emissor)[:1]
    substituida = Nfse.objects.create(
        ambiente=nota.ambiente, serie=nota.serie, competencia=EXECUCAO, valor_servico=1
    )
    Nfse.objects.filter(pk=nota.pk).update(substitui=substituida)

    sem = aprovar([nota.pk], emissor, empresa_pronta)
    com = aprovar([nota.pk], emissor, empresa_pronta, ("nfse.emitir", "nfse.substituir"))

    assert sem[0]["codigo"] == "permissao_negada" and com[0]["ok"] is True


def test_lote_vazio_ou_grande_demais_e_recusado(empresa_pronta, emissor):
    with pytest.raises(rascunhos.ErroDeRascunho, match="pelo menos um"):
        aprovar([], emissor, empresa_pronta)
    with pytest.raises(rascunhos.ErroDeRascunho, match="no máximo 100"):
        aprovar(list(range(1, 102)), emissor, empresa_pronta)


def test_repetidos_no_lote_sao_aprovados_uma_vez(empresa_pronta, modelo, emissor):
    (nota,) = tres_rascunhos(modelo, emissor)[:1]

    resultados = aprovar([nota.pk, nota.pk], emissor, empresa_pronta)

    assert len(resultados) == 1 and resultados[0]["ok"]


# -- descarte ------------------------------------------------------------------------------


def test_descartar_exige_motivo_e_guarda_no_historico(empresa_pronta, modelo, emissor):
    (nota, *_resto) = tres_rascunhos(modelo, emissor)
    with pytest.raises(rascunhos.ErroDeRascunho) as sem_motivo:
        rascunhos.descartar(nota, motivo="  ", usuario=emissor, empresa=empresa_pronta)
    assert "motivo" in sem_motivo.value.erros

    rascunhos.descartar(
        nota, motivo="Contrato encerrado em outubro", usuario=emissor, empresa=empresa_pronta
    )

    nota.refresh_from_db()
    assert nota.situacao == S.DESCARTADA
    transicao = nota.transicoes.get()
    assert transicao.motivo == "Descartado: Contrato encerrado em outubro"
    assert transicao.usuario_email == "emissor@exemplo.test"
    assert LogAuditoria.objects.filter(acao="nfse_descartada").exists()


def test_so_rascunho_pode_ser_descartado_e_descartado_nao_e_emitido(
    empresa_pronta, modelo, emissor
):
    (nota, *_resto) = tres_rascunhos(modelo, emissor)
    rascunhos.descartar(
        nota, motivo="Não será mais cobrado", usuario=emissor, empresa=empresa_pronta
    )

    with pytest.raises(rascunhos.ErroDeRascunho, match="Só um rascunho"):
        rascunhos.descartar(nota, motivo="De novo?", usuario=emissor, empresa=empresa_pronta)
    resultado = aprovar([nota.pk], emissor, empresa_pronta)[0]

    assert not resultado["ok"] and resultado["codigo"] == "nao_e_rascunho"


def test_rascunho_pendente_nunca_e_emitido_nem_apagado_sozinho(
    empresa_pronta, modelo, emissor, sefin, fila
):
    criar_agendamento(modelo, emissor, agora=utc("2026-11-01T12:00"))
    agenda.despachar(utc("2026-11-05T11:01"), empresa=empresa_pronta)

    for dia in range(6, 30):  # semanas sem ninguém aprovar
        agenda.alertar_rascunhos_pendentes(utc(f"2026-11-{dia:02d}T11:20"), empresa=empresa_pronta)

    nota = Nfse.objects.get()
    assert nota.situacao == S.RASCUNHO and sefin.total_de_posts == 0 and fila.emissoes == []


# -- alerta diário -------------------------------------------------------------------------


def test_alerta_diario_agrupa_por_responsavel_e_nao_repete_no_mesmo_dia(
    empresa_pronta, modelo, emissor
):
    configurar_email("smtp")
    outro = criar_usuario("outro@exemplo.test", empresa_pronta)
    criar_agendamento(modelo, emissor, agora=utc("2026-11-01T12:00"), nome="Mensal A")
    criar_agendamento(modelo, emissor, agora=utc("2026-11-01T12:00"), nome="Mensal B")
    criar_agendamento(modelo, outro, agora=utc("2026-11-01T12:00"), nome="Mensal C")
    agenda.despachar(utc("2026-11-05T11:01"), empresa=empresa_pronta)
    EnvioEmail.objects.all().delete()  # só interessam os alertas

    primeira = agenda.alertar_rascunhos_pendentes(utc("2026-11-06T11:20"), empresa=empresa_pronta)
    segunda = agenda.alertar_rascunhos_pendentes(utc("2026-11-06T18:00"), empresa=empresa_pronta)

    assert primeira == 2 and segunda == 2  # a segunda só devolve os mesmos registros
    alertas = EnvioEmail.objects.filter(tipo=EnvioEmail.Tipo.RASCUNHOS_PENDENTES)
    assert alertas.count() == 2  # um por responsável, mesmo repetindo no dia
    do_emissor = alertas.get(destinatarios=["emissor@exemplo.test"])
    assert "2 rascunho(s)" in do_emissor.assunto
    assert "Mensal A: 1" in do_emissor.corpo_avulso and "Mensal B: 1" in do_emissor.corpo_avulso
    agenda.alertar_rascunhos_pendentes(utc("2026-11-07T11:20"), empresa=empresa_pronta)
    assert alertas.count() == 4  # no dia seguinte, de novo


def test_alerta_so_conta_rascunhos_ainda_pendentes_de_agendamento(empresa_pronta, modelo, emissor):
    configurar_email("smtp")
    criar_agendamento(modelo, emissor, agora=utc("2026-11-01T12:00"))
    agenda.despachar(utc("2026-11-05T11:01"), empresa=empresa_pronta)
    manual = modelos.gerar_rascunho(modelo, usuario=emissor, data_execucao=EXECUCAO)  # sem agenda
    EnvioEmail.objects.all().delete()

    agenda.alertar_rascunhos_pendentes(utc("2026-11-06T11:20"), empresa=empresa_pronta)
    assert EnvioEmail.objects.get().assunto.startswith("1 rascunho")

    agendado = OrigemNfse.objects.exclude(nfse=manual).get().nfse
    rascunhos.descartar(
        agendado, motivo="Já foi cobrado fora", usuario=emissor, empresa=empresa_pronta
    )
    EnvioEmail.objects.all().delete()
    assert agenda.alertar_rascunhos_pendentes(utc("2026-11-07T11:20"), empresa=empresa_pronta) == 0
    assert EnvioEmail.objects.count() == 0


def test_sem_email_configurado_o_alerta_nao_cria_nada(empresa_pronta, modelo, emissor):
    criar_agendamento(modelo, emissor, agora=utc("2026-11-01T12:00"))
    agenda.despachar(utc("2026-11-05T11:01"), empresa=empresa_pronta)

    assert agenda.alertar_rascunhos_pendentes(utc("2026-11-06T11:20"), empresa=empresa_pronta) == 0
    assert EnvioEmail.objects.count() == 0


def test_perfil_consulta_nao_pode_ser_responsavel(empresa_pronta, modelo):
    consulta = criar_usuario("consulta@exemplo.test", empresa_pronta, Perfil.CONSULTA)

    with pytest.raises(agenda.ErroDeAgendamento):
        criar_agendamento(modelo, consulta, agora=utc("2026-11-01T12:00"))
