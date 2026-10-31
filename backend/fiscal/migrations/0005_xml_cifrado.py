"""Cifra em repouso os XMLs e as evidências já gravados (ADR 0008).

Primeiro os dados (com os campos ainda "crus"), depois a troca do tipo do campo. A conversão é
idempotente: o que já começa com `v<n>:` é um token e fica como está. Sem `FREENFSE_CHAVES`,
a migração falha em vez de deixar XML em claro. A reversão decifra, para permitir voltar atrás.
"""

import re

from django.db import migrations

import core.fields
from core import crypto

# (modelo, campo) de cada coluna que guarda XML ou evidência bruta.
COLUNAS = [
    ("Nfse", "xml_dps"),
    ("Nfse", "xml_nfse"),
    ("EventoNfse", "xml"),
    ("EvidenciaFiscal", "conteudo"),
    ("DocumentoFiscal", "xml"),
    ("EventoFiscal", "xml"),
    ("XmlNaoReconhecido", "xml"),
]
_TOKEN = re.compile(rb"v\d+:")


def _converter(apps, schema_editor, funcao, ja_convertido):
    banco = schema_editor.connection.alias
    for nome, campo in COLUNAS:
        modelo = apps.get_model("fiscal", nome)
        linhas = modelo.objects.using(banco).filter(**{f"{campo}__isnull": False})
        for pk, valor in linhas.values_list("pk", campo).iterator(chunk_size=200):
            bruto = bytes(valor)
            if ja_convertido(bruto):
                continue
            modelo.objects.using(banco).filter(pk=pk).update(**{campo: funcao(bruto)})


def cifrar(apps, schema_editor):
    """Cifra o que ainda está em claro."""
    _converter(apps, schema_editor, crypto.cifrar_bytes, lambda bruto: bool(_TOKEN.match(bruto)))


def decifrar(apps, schema_editor):
    """Volta ao claro (só para reverter a migração)."""
    _converter(apps, schema_editor, crypto.decifrar_bytes, lambda bruto: not _TOKEN.match(bruto))


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0004_ibs_cbs_por_empresa"),
    ]

    operations = [
        migrations.RunPython(cifrar, decifrar),
        migrations.AlterField(
            model_name="documentofiscal",
            name="xml",
            field=core.fields.CampoBinarioCriptografado(),
        ),
        migrations.AlterField(
            model_name="eventofiscal",
            name="xml",
            field=core.fields.CampoBinarioCriptografado(),
        ),
        migrations.AlterField(
            model_name="eventonfse",
            name="xml",
            field=core.fields.CampoBinarioCriptografado(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="evidenciafiscal",
            name="conteudo",
            field=core.fields.CampoBinarioCriptografado(),
        ),
        migrations.AlterField(
            model_name="nfse",
            name="xml_dps",
            field=core.fields.CampoBinarioCriptografado(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="nfse",
            name="xml_nfse",
            field=core.fields.CampoBinarioCriptografado(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="xmlnaoreconhecido",
            name="xml",
            field=core.fields.CampoBinarioCriptografado(),
        ),
    ]
