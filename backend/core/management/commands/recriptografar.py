"""Recriptografa com a chave atual os valores gravados com chaves antigas."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django_tenants.utils import (
    app_labels,
    get_public_schema_name,
    get_tenant_model,
    schema_context,
)

from core import crypto
from core.fields import CampoBinarioCriptografado, campos_criptografados


class Command(BaseCommand):
    """Percorre todos os campos criptografados, no schema público e em cada empresa.

    Use depois de incluir uma chave nova na frente de `FREENFSE_CHAVES`. Quando
    o comando termina sem pendências, a chave antiga pode ser removida da
    variável. É idempotente e executa cada campo/schema numa transação.
    """

    help = "Recriptografa com a chave atual os campos criptografados que usam chaves antigas."

    def add_arguments(self, parser):
        """Opções do comando."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Só conta o que seria recriptografado, sem gravar.",
        )
        parser.add_argument(
            "--lote", type=int, default=500, help="Linhas lidas por vez (padrão: 500)."
        )

    def handle(self, *args, dry_run, lote, **opcoes):
        """Executa a recriptografia e imprime um resumo por campo e schema."""
        if lote < 1:
            raise CommandError("--lote deve ser ao menos 1.")
        try:
            atual = crypto.versao_atual()
        except crypto.ErroDeCriptografia as erro:
            raise CommandError(str(erro)) from None

        compartilhados = set(app_labels(settings.SHARED_APPS))
        de_empresa = set(app_labels(settings.TENANT_APPS))
        schemas_de_empresa = list(get_tenant_model().objects.values_list("schema_name", flat=True))

        regravados = 0
        for modelo, campo in campos_criptografados():
            rotulo = modelo._meta.app_label
            schemas = []
            if rotulo in compartilhados:
                schemas.append(get_public_schema_name())
            if rotulo in de_empresa:
                schemas.extend(schemas_de_empresa)
            for schema in schemas:
                with schema_context(schema):
                    pendentes = self._processar(modelo, campo, atual, lote, dry_run)
                if pendentes:
                    self.stdout.write(
                        f"{rotulo}.{modelo.__name__}.{campo.name} [{schema}]: {pendentes}"
                    )
                regravados += pendentes

        verbo = "a recriptografar" if dry_run else "recriptografados"
        self.stdout.write(
            self.style.SUCCESS(f"Valores {verbo} para a chave v{atual}: {regravados}")
        )

    def _processar(self, modelo, campo, atual, lote, dry_run):
        """Recriptografa uma coluna do schema ativo e devolve quantos valores mudaram."""
        quote = connection.ops.quote_name
        tabela = quote(modelo._meta.db_table)
        coluna = quote(campo.column)
        chave_primaria = quote(modelo._meta.pk.column)
        binario = isinstance(campo, CampoBinarioCriptografado)
        mudados = 0
        ultimo = None

        with transaction.atomic(), connection.cursor() as cursor:
            while True:
                filtro = f"AND {chave_primaria} > %s" if ultimo is not None else ""
                parametros = ([ultimo] if ultimo is not None else []) + [lote]
                cursor.execute(
                    f"SELECT {chave_primaria}, {coluna} FROM {tabela} "  # noqa: S608 (nomes via quote_name)
                    f"WHERE {coluna} IS NOT NULL {filtro} ORDER BY {chave_primaria} LIMIT %s",
                    parametros,
                )
                linhas = cursor.fetchall()
                if not linhas:
                    break
                for pk, token in linhas:
                    ultimo = pk
                    if crypto.versao_do_token(token) == atual:
                        continue
                    novo = self._recifrar(token, binario, modelo, campo, pk)
                    mudados += 1
                    if not dry_run:
                        cursor.execute(
                            f"UPDATE {tabela} SET {coluna} = %s WHERE {chave_primaria} = %s",  # noqa: S608
                            [novo, pk],
                        )
        return mudados

    def _recifrar(self, token, binario, modelo, campo, pk):
        try:
            if binario:
                return crypto.cifrar_bytes(crypto.decifrar_bytes(token))
            return crypto.cifrar_texto(crypto.decifrar_texto(token))
        except crypto.ErroDeCriptografia as erro:
            # Identifica a linha sem expor o valor.
            raise CommandError(f"{modelo._meta.label}.{campo.name} (pk={pk}): {erro}") from None
