"""Executa funções em threads de verdade, cada uma com a sua conexão ao PostgreSQL."""

import threading

from django.db import connections
from django_tenants.utils import schema_context


def executar_em_paralelo(tarefas, *, tempo_limite=60):
    """Roda cada `(schema, funcao)` numa thread, todas largando juntas.

    Devolve `(resultados, erros)` na ordem das tarefas. A thread só termina depois de fechar a
    própria conexão (senão o banco de teste não pode ser apagado).
    """
    largada = threading.Barrier(len(tarefas))
    resultados = [None] * len(tarefas)
    erros = [None] * len(tarefas)

    def executar(indice, schema, funcao):
        try:
            with schema_context(schema):
                largada.wait(timeout=tempo_limite)
                resultados[indice] = funcao()
        except BaseException as erro:  # noqa: BLE001 - o teste confere os erros
            erros[indice] = erro
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=executar, args=(i, schema, funcao), daemon=True)
        for i, (schema, funcao) in enumerate(tarefas)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(tempo_limite)
    travadas = [t for t in threads if t.is_alive()]
    assert not travadas, f"{len(travadas)} thread(s) não terminaram em {tempo_limite}s"
    return resultados, erros
