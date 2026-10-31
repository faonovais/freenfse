"""Apoio dos testes de agendamentos: cadastros, modelos, agendamentos e usuários de teste."""

import datetime as dt

from django.db import connection

from agendamentos.models import Agendamento, ModeloNfse
from conftest import criar_usuario_de_teste
from core.models import Empresa, VinculoUsuarioEmpresa
from core.permissoes import Perfil
from fiscal.tests.apoio import criar_cadastros_de_teste

H = dt.time(8, 0)


def utc(texto):
    """Instante UTC a partir de 'AAAA-MM-DDTHH:MM'."""
    return dt.datetime.fromisoformat(texto).replace(tzinfo=dt.UTC)


def criar_modelo(**campos):
    """Modelo ativo com o tomador e o serviço de teste (no schema ativo)."""
    tomador, servico = criar_cadastros_de_teste()
    padrao = {
        "nome": "Mensalidade de consultoria",
        "tomador": tomador,
        "servico": servico,
        "valores": {"servico": "1500.00"},
        "complementos": {"informacoes_complementares": "Referente a {competencia}."},
    }
    padrao.update(campos)
    return ModeloNfse.objects.create(**padrao)


def criar_usuario(email, empresa, perfil=Perfil.EMISSOR, **vinculo):
    """Usuário com vínculo ativo (ou o que `vinculo` pedir) na empresa."""
    usuario = criar_usuario_de_teste(email)
    VinculoUsuarioEmpresa.objects.create(usuario=usuario, empresa=empresa, perfil=perfil, **vinculo)
    return usuario


def criar_agendamento(modelo, responsavel, **campos):
    """Agendamento ativo, com a próxima execução já calculada a partir de `campos['agora']`."""
    from agendamentos.services import agenda

    agora = campos.pop("agora", utc("2026-11-01T12:00"))
    dados = {
        "nome": "Cobrança mensal",
        "frequencia": Agendamento.Frequencia.MENSAL,
        "dia_do_mes": 5,
        "hora": H,
        "data_inicio": dt.date(2026, 11, 1),
    }
    dados.update(campos)
    empresa = Empresa.objects.get(schema_name=connection.schema_name)
    return agenda.salvar(
        dados,
        modelo=modelo,
        responsavel=responsavel,
        usuario=responsavel,
        empresa=empresa,
        agora=agora,
    )
