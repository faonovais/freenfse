"""Adiciona o campo opcional `nome_exibicao` no modelo Empresa."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_fase_5"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="nome_exibicao",
            field=models.CharField(blank=True, max_length=120, verbose_name="nome para exibição"),
        ),
    ]
