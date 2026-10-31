"""Backup cifrado do banco inteiro e restauração conferida (ADR 0008, Fase 6).

O backup é um `pg_dump -Fc` de **todos os schemas** (público + um por empresa) tirado sob um
instantâneo consistente (`pg_export_snapshot`), cifrado com `age` para uma **chave pública**:
o servidor só guarda o destinatário; a identidade (chave privada) fica fora dele e só serve
para restaurar. É uma chave diferente e independente de `FREENFSE_CHAVES`.

Nada aqui imprime nem registra senha, chave ou conteúdo do banco: o manifesto traz só metadados
(momento, versões, contagem de linhas por tabela, SHA-256 do arquivo cifrado).
"""

import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from django.conf import settings
from django.db import connection
from django_tenants.utils import app_labels
from psycopg import sql

from core import crypto
from core.fields import CampoBinarioCriptografado, campos_criptografados

PREFIXO = "freenfse-"
SUFIXO = ".dump.age"
FORMATO_DO_NOME = "%Y%m%dT%H%M%SZ"
_NOME = re.compile(rf"^{PREFIXO}(\d{{8}}T\d{{6}}Z){re.escape(SUFIXO)}$")
_DESTINATARIO = re.compile(r"^age1[0-9a-z]{58}$")
_CABECALHO_DO_DUMP = b"PGDMP"
_SISTEMA = ("pg_catalog", "information_schema")
VERSAO_DO_MANIFESTO = 1


class ErroDeBackup(Exception):
    """O backup não foi feito. A mensagem diz o que corrigir e nunca traz segredo."""


class ErroDeRestauracao(Exception):
    """A restauração falhou ou não passou na conferência. Nunca traz segredo nem dado."""


@dataclass(frozen=True)
class ConfigBackup:
    """Onde guardar, para quem cifrar e por quantos dias manter."""

    pasta: Path
    destinatarios: tuple[str, ...]
    retencao_dias: int = 14
    pg_dump: str = "pg_dump"
    pg_restore: str = "pg_restore"
    age: str = "age"
    banco: dict = field(default_factory=dict, repr=False)  # tem a senha: nunca no repr


def banco_atual():
    """Parâmetros de conexão do banco em uso (a senha só circula por variável de ambiente)."""
    dados = connection.settings_dict
    return {
        "dbname": dados["NAME"],
        "user": dados["USER"],
        "password": dados["PASSWORD"],
        "host": dados["HOST"] or "localhost",
        "port": str(dados["PORT"] or 5432),
    }


def config_do_ambiente():
    """Lê a configuração de `settings` (variáveis de ambiente `FREENFSE_BACKUP_*`)."""
    destinatarios = tuple(
        item.strip()
        for item in str(getattr(settings, "FREENFSE_BACKUP_DESTINATARIO", "") or "").split(",")
        if item.strip()
    )
    return ConfigBackup(
        pasta=Path(settings.FREENFSE_BACKUP_DIR),
        destinatarios=destinatarios,
        retencao_dias=int(settings.FREENFSE_BACKUP_RETENCAO_DIAS),
        banco=banco_atual(),
    )


def _ambiente(banco):
    """Variáveis de ambiente do `pg_dump`/`pg_restore`: a senha nunca vai na linha de comando."""
    ambiente = dict(os.environ)
    ambiente.update(
        PGHOST=banco["host"],
        PGPORT=banco["port"],
        PGUSER=banco["user"],
        PGPASSWORD=banco["password"],
    )
    return ambiente


def _limpar(texto, banco):
    """Mensagem de erro de ferramenta externa, sem a senha e com tamanho limitado."""
    texto = (texto or "").strip()
    if banco.get("password"):
        texto = texto.replace(banco["password"], "***")
    return texto[-600:]


def _conexao(banco, **extra):
    return psycopg.connect(
        dbname=banco["dbname"],
        user=banco["user"],
        password=banco["password"],
        host=banco["host"],
        port=banco["port"],
        **extra,
    )


def _exigir_ferramenta(nome):
    if shutil.which(nome) is None:
        raise ErroDeBackup(
            f"A ferramenta '{nome}' não está instalada neste servidor. "
            "Veja o manual de instalação (pré-requisitos do backup)."
        )


def _conferir_config(config):
    if not config.destinatarios:
        raise ErroDeBackup(
            "A chave pública do backup não está configurada (FREENFSE_BACKUP_DESTINATARIO). "
            "Gere o par de chaves fora do servidor e informe só a chave pública (age1...)."
        )
    for destinatario in config.destinatarios:
        if not _DESTINATARIO.match(destinatario):
            raise ErroDeBackup(
                "FREENFSE_BACKUP_DESTINATARIO precisa ser uma chave pública age (começa com age1). "
                "Nunca informe a chave privada (AGE-SECRET-KEY) neste servidor."
            )
    for ferramenta in (config.pg_dump, config.age):
        _exigir_ferramenta(ferramenta)
    config.pasta.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        config.pasta.chmod(0o700)
    if not os.access(config.pasta, os.W_OK):
        raise ErroDeBackup(f"A pasta de backups não é gravável: {config.pasta}")


def _contar_linhas(conn):
    """Linhas de cada tabela de todos os schemas, dentro do instantâneo aberto em `conn`."""
    tabelas = conn.execute(
        "SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.relkind = 'r' AND n.nspname <> ALL(%s) AND n.nspname NOT LIKE 'pg\\_toast%%' "
        "AND n.nspname NOT LIKE 'pg\\_temp%%' ORDER BY 1, 2",
        [list(_SISTEMA)],
    ).fetchall()
    contagem = {}
    for esquema, tabela in tabelas:
        consulta = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(esquema, tabela))
        contagem[f"{esquema}.{tabela}"] = conn.execute(consulta).fetchone()[0]
    return contagem


def _versao_da_ferramenta(comando):
    try:
        saida = subprocess.run(  # noqa: S603
            [comando, "--version"], capture_output=True, text=True, check=True, timeout=30
        ).stdout.strip()
    except OSError, subprocess.SubprocessError:
        return ""
    return saida


def _versao_do_app():
    arquivo = Path(settings.BASE_DIR).parent / "VERSION"
    try:
        return arquivo.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _dump_cifrado(config, snapshot, destino_tmp):
    """`pg_dump` -> `age`, em fluxo: o dump em claro nunca vai para o disco."""
    comando_dump = [
        config.pg_dump,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--snapshot={snapshot}",
        f"--dbname={config.banco['dbname']}",
    ]
    comando_age = [config.age]
    for destinatario in config.destinatarios:
        comando_age += ["-r", destinatario]
    comando_age += ["-o", str(destino_tmp)]
    with tempfile.TemporaryFile() as erro_dump, tempfile.TemporaryFile() as erro_age:
        age = subprocess.Popen(comando_age, stdin=subprocess.PIPE, stderr=erro_age)  # noqa: S603
        dump = subprocess.Popen(  # noqa: S603
            comando_dump,
            stdout=subprocess.PIPE,
            stderr=erro_dump,
            env=_ambiente(config.banco),
        )
        cabecalho = b""
        try:
            while pedaco := dump.stdout.read(1 << 20):
                if len(cabecalho) < len(_CABECALHO_DO_DUMP):
                    cabecalho += pedaco[: len(_CABECALHO_DO_DUMP) - len(cabecalho)]
                age.stdin.write(pedaco)
            age.stdin.close()
        except BrokenPipeError:
            dump.kill()
        codigo_dump, codigo_age = dump.wait(), age.wait()
        erro_dump.seek(0)
        erro_age.seek(0)
        texto_dump = erro_dump.read().decode("utf-8", "replace")
        texto_age = erro_age.read().decode("utf-8", "replace")
    if codigo_dump != 0:
        raise ErroDeBackup(f"O pg_dump falhou: {_limpar(texto_dump, config.banco)}")
    if codigo_age != 0:
        raise ErroDeBackup(f"A cifragem com age falhou: {_limpar(texto_age, config.banco)}")
    if cabecalho != _CABECALHO_DO_DUMP:
        raise ErroDeBackup("O pg_dump não produziu um arquivo no formato esperado.")


def _sha256_do_arquivo(caminho):
    resumo = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        while pedaco := arquivo.read(1 << 20):
            resumo.update(pedaco)
    return resumo.hexdigest()


def fazer_backup(config, *, agora=None):
    """Faz, cifra e registra um backup; depois aplica a retenção. Devolve o manifesto.

    A limpeza dos antigos só roda depois que este backup deu certo e nunca remove o mais
    recente. Em qualquer falha o arquivo parcial é apagado e `ErroDeBackup` é levantado.
    """
    _conferir_config(config)
    agora = agora or dt.datetime.now(dt.UTC)
    nome = f"{PREFIXO}{agora.strftime(FORMATO_DO_NOME)}{SUFIXO}"
    destino = config.pasta / nome
    temporario = config.pasta / f".{nome}.parcial"
    try:
        with _conexao(config.banco) as conn:
            conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            conn.read_only = True
            snapshot = conn.execute("SELECT pg_export_snapshot()").fetchone()[0]
            tabelas = _contar_linhas(conn)
            servidor = conn.execute("SHOW server_version").fetchone()[0]
            _dump_cifrado(config, snapshot, temporario)
        os.chmod(temporario, 0o600)
        os.replace(temporario, destino)
    except psycopg.Error as erro:
        raise ErroDeBackup(
            f"Não foi possível ler o banco para o backup: {_limpar(str(erro), config.banco)}"
        ) from None
    finally:
        with contextlib.suppress(OSError):
            temporario.unlink()

    manifesto = {
        "formato": VERSAO_DO_MANIFESTO,
        "criado_em": agora.isoformat(),
        "arquivo": nome,
        "tamanho": destino.stat().st_size,
        "sha256": _sha256_do_arquivo(destino),
        "versao_app": _versao_do_app(),
        "servidor": servidor,
        "pg_dump": _versao_da_ferramenta(config.pg_dump),
        "destinatarios": list(config.destinatarios),
        "esquemas": sorted({chave.split(".", 1)[0] for chave in tabelas}),
        "tabelas": tabelas,
    }
    caminho_manifesto = Path(f"{destino}.json")
    caminho_manifesto.write_text(json.dumps(manifesto, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(caminho_manifesto, 0o600)
    aplicar_retencao(config, agora=agora)
    return manifesto


def _backups(pasta):
    """`(momento, caminho)` dos backups da pasta, do mais antigo ao mais novo."""
    achados = []
    for caminho in Path(pasta).glob(f"{PREFIXO}*{SUFIXO}"):
        correspondencia = _NOME.match(caminho.name)
        if correspondencia:
            momento = dt.datetime.strptime(correspondencia.group(1), FORMATO_DO_NOME).replace(
                tzinfo=dt.UTC
            )
            achados.append((momento, caminho))
    return sorted(achados)


def aplicar_retencao(config, *, agora=None):
    """Apaga os backups mais velhos que `retencao_dias`, mantendo sempre o mais recente."""
    agora = agora or dt.datetime.now(dt.UTC)
    limite = agora - dt.timedelta(days=config.retencao_dias)
    existentes = _backups(config.pasta)
    removidos = []
    for momento, caminho in existentes[:-1]:  # o mais recente nunca sai
        if momento < limite:
            for alvo in (caminho, Path(f"{caminho}.json")):
                with contextlib.suppress(FileNotFoundError):
                    alvo.unlink()
            removidos.append(caminho.name)
    return removidos


def ultimo_backup(pasta):
    """Manifesto do backup mais recente, ou `None` se não houver nenhum."""
    existentes = _backups(pasta)
    if not existentes:
        return None
    _, caminho = existentes[-1]
    try:
        return json.loads(Path(f"{caminho}.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {"arquivo": caminho.name, "criado_em": None}


# -- restauração ---------------------------------------------------------------------------------


def _ler_manifesto(arquivo):
    caminho = Path(f"{arquivo}.json")
    try:
        manifesto = json.loads(caminho.read_text(encoding="utf-8"))
    except OSError, ValueError:
        raise ErroDeRestauracao(
            f"Não achei o manifesto do backup ({caminho.name}). Ele fica ao lado do arquivo; "
            "sem ele não há como conferir a restauração."
        ) from None
    if manifesto.get("formato") != VERSAO_DO_MANIFESTO:
        raise ErroDeRestauracao("O manifesto do backup é de um formato desconhecido.")
    return manifesto


def _criar_banco_novo(banco, destino):
    admin = {**banco, "dbname": "postgres"}
    with _conexao(admin, autocommit=True) as conn:
        existe = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [destino]).fetchone()
        if existe:
            raise ErroDeRestauracao(
                f"O banco '{destino}' já existe. A restauração só cria banco novo, para não "
                "sobrescrever dados: escolha outro nome (ou apague o banco com cuidado)."
            )
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(destino)))


def _apagar_banco(banco, destino):
    admin = {**banco, "dbname": "postgres"}
    with contextlib.suppress(psycopg.Error), _conexao(admin, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(destino))
        )


def _comentar_banco(banco, destino, texto):
    admin = {**banco, "dbname": "postgres"}
    with contextlib.suppress(psycopg.Error), _conexao(admin, autocommit=True) as conn:
        conn.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(destino), sql.Literal(texto)
            )
        )


def _restaurar_para_o_banco(config, arquivo, identidade, destino):
    """`age -d` -> `pg_restore`, em fluxo (o dump em claro não vai para o disco)."""
    banco = {**config.banco, "dbname": destino}
    comando_age = [config.age, "-d", "-i", str(identidade), str(arquivo)]
    comando_restore = [
        config.pg_restore,
        "--no-owner",
        "--no-privileges",
        "--exit-on-error",
        f"--dbname={destino}",
    ]
    with tempfile.TemporaryFile() as erro_age, tempfile.TemporaryFile() as erro_restore:
        age = subprocess.Popen(comando_age, stdout=subprocess.PIPE, stderr=erro_age)  # noqa: S603
        restore = subprocess.Popen(  # noqa: S603
            comando_restore, stdin=age.stdout, stderr=erro_restore, env=_ambiente(banco)
        )
        age.stdout.close()
        codigo_restore, codigo_age = restore.wait(), age.wait()
        erro_age.seek(0)
        erro_restore.seek(0)
        texto_age = erro_age.read().decode("utf-8", "replace")
        texto_restore = erro_restore.read().decode("utf-8", "replace")
    if codigo_age != 0:
        raise ErroDeRestauracao(
            "Não foi possível abrir o backup com a chave informada "
            f"(identidade errada ou arquivo adulterado): {_limpar(texto_age, banco)}"
        )
    if codigo_restore != 0:
        raise ErroDeRestauracao(f"O pg_restore falhou: {_limpar(texto_restore, banco)}")


def _conferir_contagens(banco_destino, manifesto):
    """Compara a contagem de linhas de cada tabela com a do manifesto (feita no backup)."""
    with _conexao(banco_destino) as conn:
        restauradas = _contar_linhas(conn)
    esperadas = manifesto["tabelas"]
    problemas = []
    for tabela in sorted(set(esperadas) | set(restauradas)):
        if esperadas.get(tabela) != restauradas.get(tabela):
            problemas.append(
                f"{tabela}: esperadas {esperadas.get(tabela, 'nenhuma')}, "
                f"restauradas {restauradas.get(tabela, 'nenhuma')}"
            )
    if problemas:
        raise ErroDeRestauracao(
            "A restauração não confere com o backup (linhas por tabela): " + "; ".join(problemas)
        )
    return sum(restauradas.values())


def _esquemas_de_empresa(conn):
    return [linha[0] for linha in conn.execute("SELECT schema_name FROM core_empresa").fetchall()]


def _conferir_campos_cifrados(banco_destino, amostra=5):
    """Decifra uma amostra dos campos cifrados com a FREENFSE_CHAVES em uso.

    O banco volta com esses campos já cifrados: sem a chave certa, XMLs e certificados não
    abrem. Esta conferência acusa isso na hora da restauração, não meses depois.
    """
    compartilhados = set(app_labels(settings.SHARED_APPS))
    decifrados = 0
    with _conexao(banco_destino) as conn:
        empresas = _esquemas_de_empresa(conn)
        for modelo, campo in campos_criptografados():
            rotulo = modelo._meta.app_label
            esquemas = ["public"] if rotulo in compartilhados else empresas
            binario = isinstance(campo, CampoBinarioCriptografado)
            for esquema in esquemas:
                consulta = sql.SQL(
                    "SELECT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL LIMIT %s"
                ).format(
                    coluna=sql.Identifier(campo.column),
                    tabela=sql.Identifier(esquema, modelo._meta.db_table),
                )
                for (valor,) in conn.execute(consulta, [amostra]).fetchall():
                    try:
                        if binario:
                            crypto.decifrar_bytes(valor)
                        else:
                            crypto.decifrar_texto(valor)
                    except crypto.ErroDeCriptografia:
                        raise ErroDeRestauracao(
                            "A FREENFSE_CHAVES informada não abre os dados restaurados "
                            f"({modelo._meta.label}.{campo.name}, schema {esquema}). "
                            "Use a mesma chave (ou o conjunto de chaves) do servidor de origem."
                        ) from None
                    decifrados += 1
    return decifrados


def restaurar_backup(config, arquivo, *, identidade, destino, agora=None):
    """Restaura o backup num banco **novo** e confere o resultado. Devolve um resumo.

    Passos: confere o SHA-256 do arquivo cifrado contra o manifesto, cria o banco `destino`
    (recusa um que já exista), decifra com a identidade `age` e restaura, compara a contagem de
    linhas de cada tabela com o manifesto e decifra uma amostra dos campos cifrados. O banco
    recebe um comentário dizendo se foi verificado; se a conferência falha, ele fica marcado
    como NÃO VERIFICADO e o erro é levantado.
    """
    arquivo = Path(arquivo)
    identidade = Path(identidade)
    for ferramenta in (config.age, config.pg_restore):
        _exigir_ferramenta(ferramenta)
    if not arquivo.is_file():
        raise ErroDeRestauracao(f"O arquivo de backup não existe: {arquivo}")
    if not identidade.is_file():
        raise ErroDeRestauracao(
            "O arquivo da chave privada do backup (identidade age) não foi encontrado. "
            "Ele deve estar guardado fora do servidor; copie-o para cá só para restaurar."
        )
    manifesto = _ler_manifesto(arquivo)
    if _sha256_do_arquivo(arquivo) != manifesto["sha256"]:
        raise ErroDeRestauracao(
            "O arquivo de backup não confere com o manifesto (SHA-256): ele está corrompido "
            "ou foi alterado. Use outra cópia."
        )

    _criar_banco_novo(config.banco, destino)
    banco_destino = {**config.banco, "dbname": destino}
    try:
        _restaurar_para_o_banco(config, arquivo, identidade, destino)
    except ErroDeRestauracao:
        _apagar_banco(config.banco, destino)  # nada útil foi restaurado: libera o nome
        raise
    try:
        linhas = _conferir_contagens(banco_destino, manifesto)
        campos = _conferir_campos_cifrados(banco_destino)
    except ErroDeRestauracao as erro:
        _comentar_banco(
            config.banco, destino, f"freenfse: restauração NÃO VERIFICADA ({erro})"[:500]
        )
        raise
    momento = (agora or dt.datetime.now(dt.UTC)).isoformat()
    _comentar_banco(
        config.banco, destino, f"freenfse: restauração verificada em {momento} ({arquivo.name})"
    )
    return {
        "banco": destino,
        "arquivo": arquivo.name,
        "tabelas": len(manifesto["tabelas"]),
        "linhas": linhas,
        "campos_cifrados_conferidos": campos,
    }
