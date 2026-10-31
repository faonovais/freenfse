"""Apoio dos testes de documentos: notas emitidas de verdade (Sefin simulada) e configurações."""

import datetime as dt
from decimal import Decimal

from documentos.models import ConfiguracaoDrive, ConfiguracaoEmail
from documentos.tests.simulados import SEGREDO_DE_TESTE, conta_de_servico_json
from fiscal.models import Nfse
from fiscal.services import emissao


def emitir(empresa, nova_nota, **ajustes):
    """Emite uma nota pelo caminho real (solicitar + executar) e devolve a nota autorizada."""
    nota = nova_nota(**ajustes)
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    assert nota.situacao == Nfse.Situacao.AUTORIZADA, nota.mensagem
    return nota


def nota_avulsa(numero, *, chave=None, emitida_em=None, situacao=Nfse.Situacao.AUTORIZADA, **extra):
    """Nota autorizada criada direto no banco (sem XML real), para testes que não geram PDF."""
    chave = chave or f"29034012{numero:042d}"[:50]
    dados = {
        "ambiente": "producao_restrita",
        "serie": 900,
        "competencia": dt.date(2026, 10, 1),
        "valor_servico": Decimal("100.00"),
        "situacao": situacao,
        "chave": chave,
        "numero_nfse": str(numero),
        "emitida_em": emitida_em or dt.datetime(2026, 11, 2, 15, 0, tzinfo=dt.UTC),
        "xml_nfse": f"<NFSe>{numero}</NFSe>".encode(),
        "tomador_nome": "TOMADOR AVULSO",
        "tomador": {"nome": "TOMADOR AVULSO", "emails_envio": ["avulso@tomador.test"]},
    }
    dados.update(extra)
    return Nfse.objects.create(**dados)


def ativar_drive(**ajustes):
    """Deixa o Drive ativo com credencial fictícia e modelos que garantem nome único."""
    configuracao = ConfiguracaoDrive.obter()
    valores = {
        "ativo": True,
        "conta_servico": conta_de_servico_json(),
        "conta_servico_email": "conta-teste@projeto-ficticio.iam.gserviceaccount.com",
        "pasta_raiz_id": "RAIZ",
        "pasta_raiz_nome": "Notas Fiscais",
        "modelo_subpastas": "{ano}/{mes}",
        "modelo_arquivo": "NFSe {numero_nfse} - {chave}",
    }
    valores.update(ajustes)
    for campo, valor in valores.items():
        setattr(configuracao, campo, valor)
    configuracao.save()
    return configuracao


def configurar_email(provedor="smtp", **ajustes):
    """Configura o e-mail da empresa com credenciais fictícias."""
    configuracao = ConfiguracaoEmail.obter()
    valores = {
        "provedor": provedor,
        "remetente_email": "notas@empresa-alfa.test",
        "remetente_nome": "Empresa Alfa",
        "smtp_host": "smtp.exemplo.test",
        "smtp_usuario": "notas@empresa-alfa.test",
        "smtp_senha": SEGREDO_DE_TESTE,
        "graph_tenant_id": "11111111-1111-1111-1111-111111111111",
        "graph_client_id": "22222222-2222-2222-2222-222222222222",
        "graph_client_secret": SEGREDO_DE_TESTE,
        "gmail_conta_servico": conta_de_servico_json(),
    }
    valores.update(ajustes)
    for campo, valor in valores.items():
        setattr(configuracao, campo, valor)
    configuracao.save()
    return configuracao
