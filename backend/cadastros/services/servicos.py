"""Gravação de serviços com a regra de vigência sem sobreposição."""

from django.db import connection, transaction


def salvar_servico(servico):
    """Valida e grava o serviço, serializando as gravações do mesmo serviço.

    A checagem de sobreposição e a gravação rodam sob um *advisory lock* da transação,
    chaveado pelo schema e pelos códigos do serviço: duas requisições simultâneas não
    conseguem criar versões sobrepostas (a verificação sozinha teria uma janela de corrida).
    """
    servico.clean()
    chave = (
        f"servico:{connection.schema_name}:"
        f"{servico.codigo_tributacao_nacional}:{servico.codigo_tributacao_municipal}"
    )
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [chave])
        servico.validar_vigencia()
        servico.save()
    return servico
