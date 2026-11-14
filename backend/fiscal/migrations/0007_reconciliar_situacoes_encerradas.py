"""Reconcilia notas autorizadas que já têm evento de cancelamento ou substituição gravado."""

import datetime as dt

from django.db import migrations
from django.utils import timezone

EVENTOS_DE_CANCELAMENTO = {"101101", "105104", "305101"}
EVENTO_DE_SUBSTITUICAO = "105102"


def _data_do_evento(origem):
    resumo = origem.resumo if isinstance(origem.resumo, dict) else {}
    bruto = resumo.get("data_evento")
    if isinstance(bruto, str) and bruto:
        try:
            return dt.datetime.fromisoformat(bruto)
        except ValueError:
            pass
    elif isinstance(bruto, dt.datetime):
        return bruto
    return origem.criado_em


def reconciliar(apps, schema_editor):
    """Atualiza a situação e os eventos de notas presas em `autorizada` após evento confirmado."""
    banco = schema_editor.connection.alias
    Nfse = apps.get_model("fiscal", "Nfse")
    EventoFiscal = apps.get_model("fiscal", "EventoFiscal")
    EventoNfse = apps.get_model("fiscal", "EventoNfse")
    TransicaoNfse = apps.get_model("fiscal", "TransicaoNfse")

    for nfse in Nfse.objects.using(banco).filter(situacao="autorizada").exclude(chave=""):
        guardados = list(
            EventoFiscal.objects.using(banco).filter(modelo="nfse", chave=nfse.chave)
        )
        for origem in guardados:
            resumo = origem.resumo if isinstance(origem.resumo, dict) else {}
            EventoNfse.objects.using(banco).get_or_create(
                nfse=nfse,
                tipo_evento=origem.tipo_evento,
                identificador=origem.identificador,
                defaults={
                    "descricao": (resumo.get("descricao") or "")[:255],
                    "registrado_em": _data_do_evento(origem),
                    "xml": bytes(origem.xml) if origem.xml else None,
                    "hash_xml": origem.sha256 or "",
                },
            )
        tipos = {e.tipo_evento for e in guardados} | set(
            EventoNfse.objects.using(banco)
            .filter(nfse=nfse)
            .values_list("tipo_evento", flat=True)
        )
        if tipos & EVENTOS_DE_CANCELAMENTO:
            nova_situacao = "cancelada"
            motivo = "Cancelamento confirmado pela Sefin"
        elif EVENTO_DE_SUBSTITUICAO in tipos:
            nova_situacao = "substituida"
            motivo = "Substituição confirmada pela Sefin"
        else:
            continue
        Nfse.objects.using(banco).filter(pk=nfse.pk, situacao="autorizada").update(
            situacao=nova_situacao,
            atualizado_em=timezone.now(),
        )
        TransicaoNfse.objects.using(banco).create(
            nfse=nfse,
            de="autorizada",
            para=nova_situacao,
            motivo=motivo,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0006_issue_29_ibs_cbs_pelo_servico"),
    ]

    operations = [
        migrations.RunPython(reconciliar, migrations.RunPython.noop),
    ]
