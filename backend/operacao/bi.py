"""Schema de leitura para BI (Fase 6): views de todas as empresas, sem XML nem segredos.

Modelo (documentado em `docs/bi.md`): o schema `bi` tem views que juntam (`UNION ALL`) as tabelas
de cada empresa, sempre com `empresa_id` e `empresa_cnpj`. Um usuário de banco **somente leitura**
(`freenfse_bi`) só enxerga o schema `bi`: não vê as tabelas das empresas, nem o schema público
(usuários e senhas), nem os XMLs ou credenciais — que também não existem nas views.

Privacidade por padrão (LGPD): o CPF do tomador sai mascarado e o nome só aparece para pessoa
jurídica. O texto livre da descrição do serviço fica de fora (pode conter dado pessoal).

As views são recriadas por `atualizar_views()` quando muda o conjunto de empresas ou uma versão
nova altera o modelo; só existem se alguém as criou (`atualizar_views_bi`/instalador).
"""

import base64
import hashlib
import hmac
import logging
import os

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

SCHEMA = "bi"
ITERACOES_SCRAM = 4096

# Cada view: colunas (nome, tipo) e o SELECT de UMA empresa. `{e}` = schema da empresa entre
# aspas; `{id}` e `{cnpj}` = identificação da empresa. As colunas definem as views vazias.
_COLUNAS_EMPRESAS = [
    ("empresa_id", "bigint"),
    ("empresa_cnpj", "varchar"),
    ("razao_social", "varchar"),
    ("ativo", "boolean"),
]

_NUM = "NULLIF({t}->>'{c}', '')::numeric"

_TOMADOR_DOC = (
    "CASE WHEN length(n.tomador_documento) = 14 THEN n.tomador_documento "
    "WHEN length(n.tomador_documento) = 11 THEN '***' || substr(n.tomador_documento, 4, 6) || '**' "
    "END"
)

_COLUNAS_NOTAS = [
    ("empresa_id", "bigint"),
    ("empresa_cnpj", "varchar"),
    ("nota_id", "bigint"),
    ("chave", "varchar"),
    ("numero_nfse", "varchar"),
    ("serie", "bigint"),
    ("numero_dps", "bigint"),
    ("situacao", "varchar"),
    ("ambiente", "varchar"),
    ("competencia", "date"),
    ("emitida_em", "timestamptz"),
    ("criada_em", "timestamptz"),
    ("atualizada_em", "timestamptz"),
    ("nota_substituida_id", "bigint"),
    ("tomador_tipo", "varchar"),
    ("tomador_documento", "varchar"),
    ("tomador_nome", "varchar"),
    ("tomador_codigo_municipio", "varchar"),
    ("valor_servico", "numeric"),
    ("desconto_incondicionado", "numeric"),
    ("desconto_condicionado", "numeric"),
    ("deducao", "numeric"),
    ("base_calculo", "numeric"),
    ("aliquota_iss", "numeric"),
    ("valor_iss", "numeric"),
    ("iss_retido", "boolean"),
    ("total_retencoes", "numeric"),
    ("valor_liquido", "numeric"),
]

_SELECT_NOTAS = f"""
SELECT {{id}}::bigint, {{cnpj}}::varchar, n.id::bigint, n.chave::varchar, n.numero_nfse::varchar,
       n.serie::bigint, n.numero_dps::bigint, n.situacao::varchar, n.ambiente::varchar,
       n.competencia, n.emitida_em, n.criado_em, n.atualizado_em, n.substitui_id::bigint,
       NULLIF(n.tomador->>'tipo', '')::varchar,
       ({_TOMADOR_DOC})::varchar,
       (CASE WHEN length(n.tomador_documento) = 14 THEN n.tomador_nome END)::varchar,
       NULLIF(n.tomador->>'codigo_municipio', '')::varchar,
       n.valor_servico,
       {_NUM.format(t="n.totais", c="desconto_incondicionado")},
       {_NUM.format(t="n.totais", c="desconto_condicionado")},
       {_NUM.format(t="n.totais", c="deducao")},
       {_NUM.format(t="n.totais", c="base_calculo")},
       {_NUM.format(t="n.totais", c="aliquota_iss")},
       {_NUM.format(t="n.totais", c="valor_iss")},
       (n.totais->>'iss_retido')::boolean,
       {_NUM.format(t="n.totais", c="total_retencoes")},
       {_NUM.format(t="n.totais", c="valor_liquido")}
FROM {{e}}.fiscal_nfse n
"""

_COLUNAS_SERVICOS = [
    ("empresa_id", "bigint"),
    ("empresa_cnpj", "varchar"),
    ("nota_id", "bigint"),
    ("situacao", "varchar"),
    ("competencia", "date"),
    ("servico_id", "bigint"),
    ("servico_nome", "varchar"),
    ("codigo_tributacao_nacional", "varchar"),
    ("codigo_tributacao_municipal", "varchar"),
    ("nbs", "varchar"),
    ("cst_ibs_cbs", "varchar"),
    ("c_class_trib", "varchar"),
    ("aliquota_iss", "numeric"),
    ("valor_servico", "numeric"),
    ("valor_iss", "numeric"),
]

_SELECT_SERVICOS = f"""
SELECT {{id}}::bigint, {{cnpj}}::varchar, n.id::bigint, n.situacao::varchar, n.competencia,
       NULLIF(n.servico->>'id', '')::bigint,
       NULLIF(n.servico->>'nome', '')::varchar,
       NULLIF(n.servico->>'codigo_tributacao_nacional', '')::varchar,
       NULLIF(n.servico->>'codigo_tributacao_municipal', '')::varchar,
       NULLIF(n.servico->>'nbs', '')::varchar,
       NULLIF(n.servico->>'cst_ibs_cbs', '')::varchar,
       NULLIF(n.servico->>'c_class_trib', '')::varchar,
       {_NUM.format(t="n.totais", c="aliquota_iss")},
       n.valor_servico,
       {_NUM.format(t="n.totais", c="valor_iss")}
FROM {{e}}.fiscal_nfse n
"""

_COLUNAS_RETENCOES = [
    ("empresa_id", "bigint"),
    ("empresa_cnpj", "varchar"),
    ("nota_id", "bigint"),
    ("situacao", "varchar"),
    ("competencia", "date"),
    ("tipo", "varchar"),
    ("valor", "numeric"),
]

# Uma linha por nota e por tipo de retenção com valor > 0. O ISS só conta se for retido.
_SELECT_RETENCOES = f"""
SELECT {{id}}::bigint, {{cnpj}}::varchar, n.id::bigint, n.situacao::varchar, n.competencia,
       r.tipo::varchar, r.valor
FROM {{e}}.fiscal_nfse n
CROSS JOIN LATERAL (VALUES
    ('iss', CASE WHEN (n.totais->>'iss_retido')::boolean
                 THEN {_NUM.format(t="n.totais", c="valor_iss")} END),
    ('irrf', {_NUM.format(t="n.totais", c="retencao_irrf")}),
    ('csll', {_NUM.format(t="n.totais", c="retencao_csll")}),
    ('inss', {_NUM.format(t="n.totais", c="retencao_inss")})
) AS r(tipo, valor)
WHERE r.valor > 0
"""

_COLUNAS_EVENTOS = [
    ("empresa_id", "bigint"),
    ("empresa_cnpj", "varchar"),
    ("evento_id", "bigint"),
    ("nota_id", "bigint"),
    ("tipo_evento", "varchar"),
    ("descricao", "varchar"),
    ("identificador", "varchar"),
    ("registrado_em", "timestamptz"),
    ("criado_em", "timestamptz"),
]

_SELECT_EVENTOS = """
SELECT {id}::bigint, {cnpj}::varchar, ev.id::bigint, ev.nfse_id::bigint, ev.tipo_evento::varchar,
       ev.descricao::varchar, ev.identificador::varchar, ev.registrado_em, ev.criado_em
FROM {e}.fiscal_eventonfse ev
"""

VIEWS = {
    "notas": (_COLUNAS_NOTAS, _SELECT_NOTAS),
    "servicos": (_COLUNAS_SERVICOS, _SELECT_SERVICOS),
    "retencoes": (_COLUNAS_RETENCOES, _SELECT_RETENCOES),
    "eventos": (_COLUNAS_EVENTOS, _SELECT_EVENTOS),
}


def usuario_de_leitura():
    """Nome do usuário de banco somente leitura (`FREENFSE_BI_USUARIO`, padrão `freenfse_bi`)."""
    return settings.FREENFSE_BI_USUARIO


def _q(nome):
    return connection.ops.quote_name(nome)


def _literal(texto):
    return "'" + str(texto).replace("'", "''") + "'"


def _vazia(colunas):
    """SELECT sem linhas com os tipos certos (usado quando ainda não há empresa)."""
    itens = ", ".join(f"NULL::{tipo} AS {_q(nome)}" for nome, tipo in colunas)
    return f"SELECT {itens} WHERE false"


def _nomes(colunas):
    return ", ".join(_q(nome) for nome, _ in colunas)


def esquema_existe():
    """Se o schema `bi` já foi criado (as views são opcionais)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", [SCHEMA])
        return cursor.fetchone() is not None


def _empresas():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, cnpj, schema_name, razao_social, ativo FROM core_empresa ORDER BY id"
        )
        return cursor.fetchall()


def _usuario_existe(cursor, nome):
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [nome])
    return cursor.fetchone() is not None


def atualizar_views():
    """Recria o schema `bi` e as views de todas as empresas (idempotente, numa transação).

    Devolve quantas empresas entraram. Os privilégios de leitura são restabelecidos ao final
    para o usuário de BI, se ele já existir.
    """
    empresas = _empresas()
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {_q(SCHEMA)}")
        # empresas
        ramos = [
            f"SELECT {empresa_id}::bigint, {_literal(cnpj)}::varchar, "
            f"{_literal(razao)}::varchar, {'true' if ativo else 'false'}::boolean"
            for empresa_id, cnpj, _schema, razao, ativo in empresas
        ]
        definicoes = {"empresas": (_COLUNAS_EMPRESAS, ramos)}
        for nome, (colunas, modelo) in VIEWS.items():
            definicoes[nome] = (
                colunas,
                [
                    modelo.format(id=empresa_id, cnpj=_literal(cnpj), e=_q(schema))
                    for empresa_id, cnpj, schema, _razao, _ativo in empresas
                ],
            )
        for nome, (colunas, ramos_da_view) in definicoes.items():
            corpo = "\nUNION ALL\n".join(ramos_da_view) if ramos_da_view else _vazia(colunas)
            cursor.execute(f"DROP VIEW IF EXISTS {_q(SCHEMA)}.{_q(nome)}")
            cursor.execute(f"CREATE VIEW {_q(SCHEMA)}.{_q(nome)} ({_nomes(colunas)}) AS\n{corpo}")
        usuario = usuario_de_leitura()
        if _usuario_existe(cursor, usuario):
            cursor.execute(f"GRANT USAGE ON SCHEMA {_q(SCHEMA)} TO {_q(usuario)}")
            cursor.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {_q(SCHEMA)} TO {_q(usuario)}")
    return len(empresas)


def atualizar_views_se_existirem():
    """Atualiza só se o schema `bi` existe; falhas são registradas e não interrompem quem chama."""
    try:
        if esquema_existe():
            return atualizar_views()
    except Exception:
        logger.exception("Não foi possível atualizar as views de BI.")
    return None


def verificador_scram(senha, *, sal=None, iteracoes=ITERACOES_SCRAM):
    """Verificador SCRAM-SHA-256 (RFC 5802/7677) da senha, no formato aceito pelo PostgreSQL.

    A senha em claro nunca vai para o servidor (nem para o log de comandos dele).
    """
    sal = sal or os.urandom(16)
    derivada = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, iteracoes)
    chave_cliente = hmac.new(derivada, b"Client Key", hashlib.sha256).digest()
    chave_armazenada = hashlib.sha256(chave_cliente).digest()
    chave_servidor = hmac.new(derivada, b"Server Key", hashlib.sha256).digest()
    b64 = base64.b64encode
    return (
        f"SCRAM-SHA-256${iteracoes}:{b64(sal).decode()}"
        f"${b64(chave_armazenada).decode()}:{b64(chave_servidor).decode()}"
    )


def criar_usuario_de_leitura(senha):
    """Cria (ou atualiza a senha d)o usuário somente leitura e libera só o schema `bi`."""
    if len(senha) < 16:
        raise ValueError("A senha do usuário de BI precisa ter pelo menos 16 caracteres.")
    usuario = usuario_de_leitura()
    banco = connection.settings_dict["NAME"]
    verificador = _literal(verificador_scram(senha))
    with connection.cursor() as cursor:
        acao = "ALTER" if _usuario_existe(cursor, usuario) else "CREATE"
        cursor.execute(
            f"{acao} ROLE {_q(usuario)} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"NOREPLICATION NOINHERIT CONNECTION LIMIT 10 PASSWORD {verificador}"
        )
        cursor.execute(f"ALTER ROLE {_q(usuario)} SET default_transaction_read_only = on")
        cursor.execute(f"ALTER ROLE {_q(usuario)} SET search_path = {_q(SCHEMA)}")
        cursor.execute(f"ALTER ROLE {_q(usuario)} SET statement_timeout = '120s'")
        cursor.execute(f"ALTER ROLE {_q(usuario)} SET idle_in_transaction_session_timeout = '60s'")
        cursor.execute(f"GRANT CONNECT ON DATABASE {_q(banco)} TO {_q(usuario)}")
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {_q(SCHEMA)}")
    atualizar_views()  # concede o SELECT agora que o usuário existe
    return usuario
