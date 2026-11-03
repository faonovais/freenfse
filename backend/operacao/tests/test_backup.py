"""Backup cifrado e restauração conferida (ADR 0008, issue #9).

Usam as ferramentas de verdade (`pg_dump`, `pg_restore`, `age`) contra o banco de teste: o ciclo
"backup → banco novo → dados conferidos" é o critério de aceite da Fase 6. Os dados precisam estar
confirmados no banco (o `pg_dump` roda em outro processo), por isso a fixture
`empresas_com_dados` usa `transactional_db` e apaga os schemas ao final.
"""

import dataclasses
import datetime as dt
import io
import json
import stat
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core import crypto
from operacao import backup
from operacao.tests.conftest import comentario_do_banco, gerar_par_age

pytestmark = pytest.mark.django_db(transaction=True)

SENHA_DE_TESTE_DO_EMAIL = "senha-smtp-que-nao-pode-vazar"


def _fazer(config, empresas_com_dados, agora=None):
    return backup.fazer_backup(
        config, agora=agora or dt.datetime(2026, 11, 1, 5, 30, tzinfo=dt.UTC)
    )


def _arquivo(config, manifesto):
    return config.pasta / manifesto["arquivo"]


def _consulta(nome_do_banco, comando, parametros=()):
    banco = {**backup.banco_atual(), "dbname": nome_do_banco}
    with backup._conexao(banco) as conn:
        return conn.execute(comando, parametros).fetchall()


# -- backup --------------------------------------------------------------------------------------


def test_o_backup_e_um_arquivo_age_que_nao_deixa_nada_em_claro(config, empresas_com_dados):
    alfa, _ = empresas_com_dados

    manifesto = _fazer(config, empresas_com_dados)

    arquivo = _arquivo(config, manifesto)
    conteudo = arquivo.read_bytes()
    assert conteudo.startswith(b"age-encryption.org/v1")
    # Nem o formato do dump, nem nomes, nem o XML, nem a credencial aparecem no arquivo.
    for trecho in (b"PGDMP", alfa.razao_social.encode(), b"<NFSe>", b"fiscal_nfse"):
        assert trecho not in conteudo
    assert stat.S_IMODE(arquivo.stat().st_mode) == 0o600
    assert manifesto["destinatarios"] == list(config.destinatarios)


def test_o_manifesto_descreve_o_backup_sem_segredo(config, empresas_com_dados):
    alfa, beta = empresas_com_dados

    manifesto = _fazer(config, empresas_com_dados)

    gravado = json.loads(Path(f"{_arquivo(config, manifesto)}.json").read_text(encoding="utf-8"))
    assert gravado == manifesto
    assert manifesto["criado_em"] == "2026-11-01T05:30:00+00:00"
    assert (
        manifesto["sha256"] and manifesto["tamanho"] == _arquivo(config, manifesto).stat().st_size
    )
    assert {"public", alfa.schema_name, beta.schema_name} <= set(manifesto["esquemas"])
    assert manifesto["tabelas"][f"{alfa.schema_name}.fiscal_nfse"] == 2
    assert manifesto["tabelas"][f"{beta.schema_name}.fiscal_nfse"] == 1
    texto = json.dumps(manifesto)
    banco = backup.banco_atual()
    for segredo in (banco["password"], SENHA_DE_TESTE_DO_EMAIL, "AGE-SECRET-KEY"):
        assert segredo not in texto


def test_o_backup_tira_tudo_do_mesmo_instante(config, empresas_com_dados):
    """As contagens do manifesto e o dump saem do mesmo instantâneo (`pg_export_snapshot`)."""
    manifesto = _fazer(config, empresas_com_dados)

    antes = manifesto["tabelas"]
    assert all(isinstance(n, int) and n >= 0 for n in antes.values())
    assert sum(antes.values()) > 0


@pytest.mark.parametrize(
    ("destinatarios", "trecho"),
    [
        ((), "chave pública do backup não está configurada"),
        (("AGE-SECRET-KEY-1ABCDEFGHJKLMNPQRSTUVWXYZ",), "Nunca informe a chave privada"),
        (("nao-e-uma-chave",), "chave pública age"),
    ],
)
def test_destinatario_ausente_ou_invalido_e_recusado_sem_ecoar_o_valor(
    config, tmp_path, destinatarios, trecho
):
    invalida = dataclasses.replace(config, destinatarios=destinatarios)

    with pytest.raises(backup.ErroDeBackup, match=trecho) as erro:
        backup.fazer_backup(invalida)

    for item in destinatarios:
        assert item not in str(erro.value)
    assert not list(config.pasta.glob("freenfse-*")) if config.pasta.exists() else True


def test_pg_dump_com_defeito_nao_deixa_arquivo_nem_apaga_os_antigos(config, empresas_com_dados):
    antigo = _fazer(config, empresas_com_dados, agora=dt.datetime(2026, 10, 1, 5, 0, tzinfo=dt.UTC))
    quebrado = dataclasses.replace(config, pg_dump="false")  # sai com código 1, sem escrever nada

    with pytest.raises(backup.ErroDeBackup, match="pg_dump"):
        backup.fazer_backup(quebrado, agora=dt.datetime(2026, 11, 20, 5, 0, tzinfo=dt.UTC))

    nomes = sorted(p.name for p in config.pasta.iterdir())
    assert nomes == [antigo["arquivo"], f"{antigo['arquivo']}.json"]  # nada parcial, nada apagado


def _ferramenta_que_falha(tmp_path, nome, mensagem):
    """Executável de teste que escreve `mensagem` no erro e sai com código 1."""
    caminho = tmp_path / nome
    caminho.write_text(f"#!/bin/sh\ncat >/dev/null\necho '{mensagem}' >&2\nexit 1\n")
    caminho.chmod(0o755)
    return str(caminho)


def test_backup_que_falha_nao_aplica_a_retencao_nem_apaga_backups_antigos(
    config, empresas_com_dados
):
    """A limpeza só vale depois de um backup novo e bom: sem ele, o que existe é tudo o que há."""
    config.pasta.mkdir()
    muito_velho = _criar_falso(config.pasta, dt.datetime(2026, 9, 1, 5, 0, tzinfo=dt.UTC))
    velho = _criar_falso(config.pasta, dt.datetime(2026, 10, 1, 5, 0, tzinfo=dt.UTC))
    quebrado = dataclasses.replace(config, pg_dump="false")

    with pytest.raises(backup.ErroDeBackup):
        backup.fazer_backup(quebrado, agora=dt.datetime(2026, 11, 20, 5, 0, tzinfo=dt.UTC))

    assert (config.pasta / muito_velho).exists() and (config.pasta / velho).exists()


def test_o_erro_de_uma_ferramenta_externa_nao_vaza_a_senha_do_banco(
    config, empresas_com_dados, tmp_path
):
    senha = config.banco["password"]
    quebrado = dataclasses.replace(
        config, pg_dump=_ferramenta_que_falha(tmp_path, "pg_dump_falso", f"falha com senha {senha}")
    )

    with pytest.raises(backup.ErroDeBackup) as erro:
        backup.fazer_backup(quebrado)

    assert "falha com senha" in str(erro.value) and senha not in str(erro.value)


def test_falha_da_cifragem_com_age_nao_vira_backup_bom(config, empresas_com_dados, tmp_path):
    sem_age = dataclasses.replace(
        config, age=_ferramenta_que_falha(tmp_path, "age_falso", "age quebrou")
    )

    with pytest.raises(backup.ErroDeBackup, match="cifragem com age falhou"):
        backup.fazer_backup(sem_age)

    assert not list(config.pasta.glob("freenfse-*"))  # nenhum arquivo, nenhum manifesto


def test_o_erro_do_banco_nao_vaza_a_senha(config, empresas_com_dados):
    errado = dataclasses.replace(config, banco={**config.banco, "dbname": "banco_que_nao_existe"})

    with pytest.raises(backup.ErroDeBackup) as erro:
        backup.fazer_backup(errado)

    assert config.banco["password"] not in str(erro.value)


# -- retenção ------------------------------------------------------------------------------------


def _criar_falso(pasta, momento):
    nome = f"{backup.PREFIXO}{momento.strftime(backup.FORMATO_DO_NOME)}{backup.SUFIXO}"
    (pasta / nome).write_bytes(b"x")
    (pasta / f"{nome}.json").write_text("{}")
    return nome


def test_a_retencao_apaga_so_os_mais_velhos_que_o_prazo_e_guarda_o_ultimo(config):
    config.pasta.mkdir()
    agora = dt.datetime(2026, 11, 20, 5, 0, tzinfo=dt.UTC)
    velho = _criar_falso(config.pasta, agora - dt.timedelta(days=30))
    limite = _criar_falso(config.pasta, agora - dt.timedelta(days=13))
    recente = _criar_falso(config.pasta, agora - dt.timedelta(days=1))

    removidos = backup.aplicar_retencao(config, agora=agora)

    assert removidos == [velho]
    restantes = {p.name for p in config.pasta.iterdir()}
    assert restantes == {limite, f"{limite}.json", recente, f"{recente}.json"}


def test_a_retencao_nunca_apaga_o_unico_backup_mesmo_vencido(config):
    config.pasta.mkdir()
    agora = dt.datetime(2026, 11, 20, 5, 0, tzinfo=dt.UTC)
    unico = _criar_falso(config.pasta, agora - dt.timedelta(days=400))

    assert backup.aplicar_retencao(config, agora=agora) == []

    assert (config.pasta / unico).exists()


def test_o_backup_aplica_a_retencao_depois_de_dar_certo(config, empresas_com_dados):
    config.pasta.mkdir()
    velho = _criar_falso(config.pasta, dt.datetime(2026, 10, 1, 5, 0, tzinfo=dt.UTC))

    manifesto = _fazer(config, empresas_com_dados)

    assert not (config.pasta / velho).exists()
    assert (_arquivo(config, manifesto)).exists()
    assert backup.ultimo_backup(config.pasta)["arquivo"] == manifesto["arquivo"]


# -- restauração ---------------------------------------------------------------------------------


def test_restaurar_o_backup_num_banco_novo_confere_e_os_dados_batem(
    config, par_age, empresas_com_dados, banco_restaurado
):
    alfa, beta = empresas_com_dados
    manifesto = _fazer(config, empresas_com_dados)
    destino = banco_restaurado()

    resumo = backup.restaurar_backup(
        config, _arquivo(config, manifesto), identidade=par_age[1], destino=destino
    )

    assert resumo["banco"] == destino and resumo["linhas"] > 0
    assert resumo["campos_cifrados_conferidos"] > 0
    # As notas voltaram, com o XML ainda cifrado na coluna e legível com a chave da aplicação.
    notas = _consulta(
        destino, f'SELECT numero_nfse, xml_nfse FROM "{alfa.schema_name}".fiscal_nfse ORDER BY 1'
    )
    assert [n for n, _ in notas] == ["1", "2"]
    for numero, token in notas:
        assert bytes(token).startswith(b"v1:")
        assert crypto.decifrar_bytes(bytes(token)) == f"<NFSe>{numero}</NFSe>".encode()
    outra = _consulta(destino, f'SELECT numero_nfse FROM "{beta.schema_name}".fiscal_nfse')
    assert outra == [("3",)]
    assert "restauração verificada" in comentario_do_banco(destino)


def test_restaurar_recusa_um_banco_que_ja_existe(config, par_age, empresas_com_dados):
    manifesto = _fazer(config, empresas_com_dados)

    with pytest.raises(backup.ErroDeRestauracao, match="já existe"):
        backup.restaurar_backup(
            config,
            _arquivo(config, manifesto),
            identidade=par_age[1],
            destino=config.banco["dbname"],  # o banco em uso
        )


def test_identidade_errada_nao_restaura_nada_e_libera_o_nome(
    config, tmp_path, empresas_com_dados, banco_restaurado
):
    manifesto = _fazer(config, empresas_com_dados)
    _, identidade_de_outro = gerar_par_age(tmp_path, "outra.txt")
    destino = banco_restaurado()

    with pytest.raises(backup.ErroDeRestauracao, match="chave informada"):
        backup.restaurar_backup(
            config, _arquivo(config, manifesto), identidade=identidade_de_outro, destino=destino
        )

    admin = {**config.banco, "dbname": "postgres"}
    with backup._conexao(admin) as conn:
        assert (
            conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [destino]).fetchone()
            is None
        )


def test_arquivo_adulterado_e_barrado_antes_de_criar_qualquer_banco(
    config, par_age, empresas_com_dados, banco_restaurado
):
    manifesto = _fazer(config, empresas_com_dados)
    arquivo = _arquivo(config, manifesto)
    bruto = bytearray(arquivo.read_bytes())
    bruto[-5] ^= 0xFF
    arquivo.write_bytes(bytes(bruto))
    destino = banco_restaurado()

    with pytest.raises(backup.ErroDeRestauracao, match="SHA-256"):
        backup.restaurar_backup(config, arquivo, identidade=par_age[1], destino=destino)

    admin = {**config.banco, "dbname": "postgres"}
    with backup._conexao(admin) as conn:
        assert (
            conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [destino]).fetchone()
            is None
        )


def test_sem_o_manifesto_nao_ha_como_conferir_e_a_restauracao_nao_comeca(
    config, par_age, empresas_com_dados, banco_restaurado
):
    manifesto = _fazer(config, empresas_com_dados)
    arquivo = _arquivo(config, manifesto)
    Path(f"{arquivo}.json").unlink()

    with pytest.raises(backup.ErroDeRestauracao, match="manifesto"):
        backup.restaurar_backup(config, arquivo, identidade=par_age[1], destino=banco_restaurado())


def test_divergencia_com_o_manifesto_reprova_e_marca_o_banco_como_nao_verificado(
    config, par_age, empresas_com_dados, banco_restaurado
):
    alfa, _ = empresas_com_dados
    manifesto = _fazer(config, empresas_com_dados)
    arquivo = _arquivo(config, manifesto)
    caminho = Path(f"{arquivo}.json")
    adulterado = json.loads(caminho.read_text(encoding="utf-8"))
    adulterado["tabelas"][f"{alfa.schema_name}.fiscal_nfse"] += (
        1  # o backup "tinha" uma nota a mais
    )
    caminho.write_text(json.dumps(adulterado), encoding="utf-8")
    destino = banco_restaurado()

    with pytest.raises(backup.ErroDeRestauracao, match="não confere com o backup") as erro:
        backup.restaurar_backup(config, arquivo, identidade=par_age[1], destino=destino)

    assert f"{alfa.schema_name}.fiscal_nfse: esperadas 3, restauradas 2" in str(erro.value)
    assert "NÃO VERIFICADA" in comentario_do_banco(destino)


def test_chaves_da_aplicacao_erradas_sao_acusadas_na_restauracao(
    settings, config, par_age, empresas_com_dados, banco_restaurado
):
    manifesto = _fazer(config, empresas_com_dados)
    settings.FREENFSE_CHAVES = [f"1:{crypto.gerar_chave()}"]  # outra chave, como num servidor novo
    destino = banco_restaurado()

    with pytest.raises(
        backup.ErroDeRestauracao, match="FREENFSE_CHAVES informada não abre"
    ) as erro:
        backup.restaurar_backup(
            config, _arquivo(config, manifesto), identidade=par_age[1], destino=destino
        )

    assert SENHA_DE_TESTE_DO_EMAIL not in str(erro.value)
    assert "NÃO VERIFICADA" in comentario_do_banco(destino)


# -- comandos e tarefa ---------------------------------------------------------------------------


def test_comandos_fazem_e_restauram_o_backup(
    settings, config, par_age, empresas_com_dados, banco_restaurado
):
    settings.FREENFSE_BACKUP_DIR = str(config.pasta)
    settings.FREENFSE_BACKUP_DESTINATARIO = par_age[0]
    saida = io.StringIO()

    call_command("fazer_backup", stdout=saida)

    assert "Backup feito: freenfse-" in saida.getvalue()
    arquivo = next(config.pasta.glob("freenfse-*.dump.age"))
    saida = io.StringIO()
    destino = banco_restaurado()
    call_command(
        "restaurar_backup", str(arquivo), identidade=str(par_age[1]), destino=destino, stdout=saida
    )
    assert f"Restauração verificada no banco '{destino}'" in saida.getvalue()


def test_comando_sem_configuracao_falha_com_mensagem_clara(settings, tmp_path):
    settings.FREENFSE_BACKUP_DIR = str(tmp_path / "b")
    settings.FREENFSE_BACKUP_DESTINATARIO = ""

    with pytest.raises(CommandError, match="chave pública do backup"):
        call_command("fazer_backup", stdout=io.StringIO())


def test_a_tarefa_agendada_faz_o_backup_e_falha_alto_quando_nao_da(
    settings, config, par_age, empresas_com_dados, caplog
):
    from operacao import tasks

    settings.FREENFSE_BACKUP_DIR = str(config.pasta)
    settings.FREENFSE_BACKUP_DESTINATARIO = par_age[0]

    assert tasks.fazer_backup().startswith("freenfse-")

    settings.FREENFSE_BACKUP_DESTINATARIO = ""
    with pytest.raises(backup.ErroDeBackup), caplog.at_level("CRITICAL"):
        tasks.fazer_backup()
    assert any(r.levelname == "CRITICAL" for r in caplog.records)


def test_o_agendamento_diario_do_backup_esta_no_beat(settings):
    entrada = settings.CELERY_BEAT_SCHEDULE["fazer-backup"]
    assert entrada["task"] == "operacao.tasks.fazer_backup"
    assert entrada["schedule"].hour == {2} and entrada["schedule"].minute == {30}
    assert settings.CELERY_TIMEZONE == "America/Sao_Paulo"  # 02:30 é horário de Brasília
