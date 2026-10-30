import pytest
from django.test import RequestFactory

from core.models import LogAuditoria
from core.services import auditoria

Acao = LogAuditoria.Acao


def test_registro_guarda_usuario_empresa_master_ip_e_detalhes(master, empresa_a):
    pedido = RequestFactory().get("/", REMOTE_ADDR="198.51.100.9")
    pedido.user = master
    pedido.empresa = empresa_a

    registro = auditoria.registrar(Acao.LOGIN, request=pedido, alvo="Usuario:1", detalhes={"a": 1})

    assert registro.usuario == master and registro.usuario_snapshot == master.email
    assert registro.empresa == empresa_a and registro.empresa_snapshot == empresa_a.cnpj
    assert registro.master is True
    assert registro.ip == "198.51.100.9"
    assert registro.detalhes == {"a": 1}


def test_registro_sem_pedido_nem_usuario_funciona(db):
    registro = auditoria.registrar(Acao.LOGIN_FALHOU, alvo="login")

    assert registro.usuario is None and registro.ip is None and registro.master is False


def test_registro_nao_pode_ser_alterado_nem_apagado(master):
    registro = auditoria.registrar(Acao.LOGIN, usuario=master)

    registro.alvo = "adulterado"
    with pytest.raises(PermissionError):
        registro.save()
    with pytest.raises(PermissionError):
        registro.delete()
    with pytest.raises(PermissionError):
        LogAuditoria.objects.all().update(alvo="adulterado")
    with pytest.raises(PermissionError):
        LogAuditoria.objects.all().delete()
    assert LogAuditoria.objects.get(pk=registro.pk).alvo == ""


def test_snapshot_preserva_a_identificacao_se_o_usuario_for_removido(usuario):
    registro = auditoria.registrar(Acao.LOGIN, usuario=usuario)

    usuario.delete()

    registro = LogAuditoria.objects.get(pk=registro.pk)
    assert registro.usuario is None
    assert registro.usuario_snapshot == "usuario@exemplo.test"


def test_alvo_longo_e_truncado(db):
    registro = auditoria.registrar(Acao.LOGIN, alvo="x" * 500)

    assert len(registro.alvo) == 120
