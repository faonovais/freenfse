"""Fixtures dos testes de operação: banco com dados confirmados, chaves age e bancos restaurados."""

import shutil
import subprocess
import uuid

import psycopg
import pytest
from django_tenants.utils import schema_context
from psycopg import sql

from conftest import CNPJ_A, CNPJ_B
from core.models import Empresa
from operacao import backup

pytestmark = pytest.mark.django_db


def gerar_par_age(pasta, nome="identidade.txt"):
    """Cria um par de chaves age de teste e devolve `(chave_publica, caminho_da_identidade)`."""
    caminho = pasta / nome
    subprocess.run(["age-keygen", "-o", str(caminho)], check=True, capture_output=True)  # noqa: S607
    publica = subprocess.run(  # noqa: S603
        ["age-keygen", "-y", str(caminho)],
        check=True,
        capture_output=True,
        text=True,  # noqa: S607
    ).stdout.strip()
    return publica, caminho


@pytest.fixture(autouse=True)
def _ferramentas():
    """Os testes de backup precisam das ferramentas reais; sem elas, falham (nunca 'passam')."""
    ausentes = [f for f in ("pg_dump", "pg_restore", "age", "age-keygen") if not shutil.which(f)]
    assert not ausentes, f"Ferramentas ausentes para os testes de backup: {ausentes}"


@pytest.fixture
def par_age(tmp_path):
    return gerar_par_age(tmp_path)


@pytest.fixture
def config(tmp_path, par_age):
    return backup.ConfigBackup(
        pasta=tmp_path / "backups",
        destinatarios=(par_age[0],),
        retencao_dias=14,
        banco=backup.banco_atual(),
    )


@pytest.fixture
def empresas_com_dados(transactional_db):
    """Duas empresas com XML e credencial **confirmados** (o `pg_dump` é outro processo)."""
    from documentos.tests.apoio import configurar_email, nota_avulsa

    alfa = Empresa.objects.create(razao_social="Empresa Alfa Teste Ltda", cnpj=CNPJ_A)
    beta = Empresa.objects.create(razao_social="Empresa Beta Teste Ltda", cnpj=CNPJ_B)
    with schema_context(alfa.schema_name):
        nota_avulsa(1)
        nota_avulsa(2)
        configurar_email("smtp")
    with schema_context(beta.schema_name):
        nota_avulsa(3)
    yield alfa, beta
    for empresa in (alfa, beta):
        empresa.delete(force_drop=True)


@pytest.fixture
def banco_restaurado():
    """Gera nomes de bancos de destino e os apaga ao final, existam ou não."""
    criados = []

    def _nome():
        nome = f"restaurado_{uuid.uuid4().hex[:12]}"
        criados.append(nome)
        return nome

    yield _nome
    admin = {**backup.banco_atual(), "dbname": "postgres"}
    for nome in criados:
        with backup._conexao(admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def comentario_do_banco(nome):
    admin = {**backup.banco_atual(), "dbname": "postgres"}
    with psycopg.connect(**{**_kw(admin)}) as conn:
        return conn.execute(
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s",
            [nome],
        ).fetchone()[0]


def _kw(banco):
    return {k: banco[k] for k in ("dbname", "user", "password", "host", "port")}
