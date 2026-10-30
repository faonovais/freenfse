"""Perfis de pessoa padrão (cliente, fornecedor, intermediário) em cada empresa."""

from django.db import migrations

PERFIS_PADRAO = [
    ("cliente", "Cliente"),
    ("fornecedor", "Fornecedor"),
    ("intermediario", "Intermediário"),
]


def criar_perfis_padrao(apps, schema_editor):
    """Cria os perfis padrão, sem duplicar se já existirem."""
    PerfilPessoa = apps.get_model("cadastros", "PerfilPessoa")
    for codigo, nome in PERFIS_PADRAO:
        PerfilPessoa.objects.get_or_create(codigo=codigo, defaults={"nome": nome, "sistema": True})


class Migration(migrations.Migration):
    dependencies = [("cadastros", "0001_initial")]

    operations = [migrations.RunPython(criar_perfis_padrao, migrations.RunPython.noop)]
