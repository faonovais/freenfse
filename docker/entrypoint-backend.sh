#!/bin/sh
# Prepara o backend e executa o comando do contêiner.
# Só o serviço "backend" aplica migrações (EXECUTAR_MIGRACOES=1); worker e beat
# apenas aguardam o backend ficar saudável.
set -eu

if [ "${EXECUTAR_MIGRACOES:-0}" = "1" ]; then
    python manage.py migrate_schemas --noinput
fi

exec "$@"
