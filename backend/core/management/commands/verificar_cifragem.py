"""Confere, lendo a coluna **bruta**, que nenhum campo criptografado está em claro."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django_tenants.utils import (
    app_labels,
    get_public_schema_name,
    get_tenant_model,
    schema_context,
)

from core.fields import CampoBinarioCriptografado, campos_criptografados

# Um valor cifrado começa com `v<versão>:` (ver `core.crypto`).
PADRAO_DO_TOKEN = "^v[0-9]+:"


class Command(BaseCommand):
    """Percorre todos os campos criptografados, no schema público e em cada empresa.

    A leitura é por SQL, sem passar pelo campo do modelo (que decifraria e esconderia o
    problema). Termina com erro se achar qualquer valor em claro: use depois da migração que
    cifra os XMLs e na verificação final da instalação. Não imprime nenhum valor.
    """

    help = "Acusa qualquer valor em claro nos campos criptografados (leitura da coluna bruta)."

    def handle(self, *args, **opcoes):
        """Confere cada coluna de cada schema e resume o resultado."""
        compartilhados = set(app_labels(settings.SHARED_APPS))
        de_empresa = set(app_labels(settings.TENANT_APPS))
        schemas_de_empresa = list(get_tenant_model().objects.values_list("schema_name", flat=True))

        conferidos = 0
        em_claro = 0
        for modelo, campo in campos_criptografados():
            rotulo = modelo._meta.app_label
            schemas = []
            if rotulo in compartilhados:
                schemas.append(get_public_schema_name())
            if rotulo in de_empresa:
                schemas.extend(schemas_de_empresa)
            for schema in schemas:
                with schema_context(schema):
                    total, claros = self._contar(modelo, campo)
                conferidos += total
                if claros:
                    em_claro += claros
                    local = f"{modelo._meta.label}.{campo.name} [{schema}]"
                    self.stderr.write(f"EM CLARO: {local}: {claros} de {total}")

        if em_claro:
            raise CommandError(
                f"{em_claro} valor(es) em claro em campo criptografado. "
                "Rode `python manage.py migrate_schemas` com a FREENFSE_CHAVES configurada."
            )
        self.stdout.write(
            self.style.SUCCESS(f"Todos os {conferidos} valores conferidos estão cifrados.")
        )

    @staticmethod
    def _contar(modelo, campo):
        """`(valores preenchidos, valores que não parecem um token)` da coluna do schema ativo."""
        quote = connection.ops.quote_name
        tabela = quote(modelo._meta.db_table)
        coluna = quote(campo.column)
        # Em bytea, `encode(..., 'escape')` dos primeiros bytes permite comparar com o texto.
        if isinstance(campo, CampoBinarioCriptografado):
            inicio = f"encode(substring({coluna} from 1 for 24), 'escape')"
        else:
            inicio = f"left({coluna}, 24)"
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*), count(*) FILTER (WHERE {inicio} !~ %s) "  # noqa: S608 (quote_name)
                f"FROM {tabela} WHERE {coluna} IS NOT NULL",
                [PADRAO_DO_TOKEN],
            )
            return cursor.fetchone()
