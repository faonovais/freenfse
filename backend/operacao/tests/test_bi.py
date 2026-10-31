"""Views para BI (Fase 6): consolidam as empresas, só leitura, sem XML nem credenciais."""

import datetime as dt
import io
import re
import uuid
from decimal import Decimal

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django_tenants.utils import schema_context
from psycopg import sql

from conftest import CNPJ_A, CNPJ_B, cnpj_de_teste
from core.models import Empresa
from fiscal.models import EventoNfse, Nfse
from operacao import backup, bi

pytestmark = pytest.mark.django_db(transaction=True)
SENHA = "senha-de-bi-do-teste-0123456789"
CNPJ_C = cnpj_de_teste("115556660001")  # terceira empresa, distinta de CNPJ_A e CNPJ_B


def _admin(conn_kw=None):
    return {**backup.banco_atual(), "dbname": "postgres"}


def _limpar(usuario):
    """Remove o schema bi e o usuário de teste (o usuário é global do servidor)."""
    banco = backup.banco_atual()
    with backup._conexao(banco, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS bi CASCADE")
        existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [usuario]).fetchone()
        if existe:
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(usuario)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(usuario)))


@pytest.fixture
def usuario_bi(settings):
    nome = f"bi_teste_{uuid.uuid4().hex[:8]}"
    settings.FREENFSE_BI_USUARIO = nome
    yield nome
    _limpar(nome)


@pytest.fixture
def bi_pronto(empresas_com_dados, usuario_bi):
    """Empresas com dados confirmados + usuário de leitura + views criadas."""
    bi.criar_usuario_de_leitura(SENHA)
    return usuario_bi


def _como_bi(usuario, **extra):
    banco = backup.banco_atual()
    return psycopg.connect(
        dbname=banco["dbname"],
        user=usuario,
        password=SENHA,
        host=banco["host"],
        port=banco["port"],
        **extra,
    )


def _nota(**extra):
    dados = {
        "ambiente": "producao",
        "serie": 1,
        "competencia": dt.date(2026, 10, 1),
        "valor_servico": Decimal("1000.00"),
        "situacao": Nfse.Situacao.AUTORIZADA,
        "chave": uuid.uuid4().hex + uuid.uuid4().hex[:18],
        "numero_nfse": "10",
        "xml_nfse": b"<NFSe>conteudo-que-nao-pode-aparecer-no-bi</NFSe>",
        "tomador": {"tipo": "pj", "codigo_municipio": "2903201"},
        "tomador_documento": "11222333000262",
        "tomador_nome": "TOMADOR PJ LTDA",
        "totais": {
            "valor_servico": "1000.00",
            "base_calculo": "1000.00",
            "aliquota_iss": "2.00",
            "valor_iss": "20.00",
            "iss_retido": False,
            "retencao_irrf": "0.00",
            "retencao_csll": "0.00",
            "retencao_inss": "0.00",
            "total_retencoes": "0.00",
            "valor_liquido": "1000.00",
        },
        "servico": {"id": 7, "nome": "Consultoria", "codigo_tributacao_nacional": "170101"},
    }
    dados.update(extra)
    return Nfse.objects.create(**dados)


# -- o que as views mostram ----------------------------------------------------------------------


def test_as_views_consolidam_as_empresas_com_o_identificador_de_cada_uma(
    bi_pronto, empresas_com_dados
):
    alfa, beta = empresas_com_dados
    with _como_bi(bi_pronto) as conn:
        empresas = conn.execute("SELECT empresa_cnpj, ativo FROM bi.empresas ORDER BY 1").fetchall()
        por_empresa = dict(
            conn.execute("SELECT empresa_cnpj, count(*) FROM bi.notas GROUP BY 1").fetchall()
        )
        colunas = {
            linha[0]
            for linha in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'bi' AND table_name = 'notas'"
            )
        }

    assert empresas == [(CNPJ_A, True), (CNPJ_B, True)]
    assert por_empresa == {alfa.cnpj: 2, beta.cnpj: 1}
    assert {"empresa_id", "empresa_cnpj", "nota_id", "valor_servico", "valor_iss"} <= colunas


def test_usuario_de_bi_so_le_o_schema_bi_e_nao_escreve(bi_pronto, empresas_com_dados):
    alfa, _ = empresas_com_dados
    with _como_bi(bi_pronto) as conn:
        assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
        assert conn.execute("SHOW search_path").fetchone()[0] == "bi"
        assert conn.execute("SELECT count(*) FROM notas").fetchone()[0] == 3  # via search_path

    # Fora do schema bi: nada é lido nem escrito (cada tentativa tem de falhar, sozinha).
    proibido = [
        "SELECT * FROM public.core_usuario",
        "SELECT * FROM public.core_empresa",
        f'SELECT * FROM "{alfa.schema_name}".fiscal_nfse',
        f'SELECT xml_nfse FROM "{alfa.schema_name}".fiscal_nfse',
        "CREATE TABLE bi.invasor (a int)",
        "CREATE TABLE public.invasor (a int)",
        "INSERT INTO bi.empresas VALUES (1, 'x', 'x', true)",
        "UPDATE bi.notas SET situacao = 'x'",
        "DELETE FROM bi.notas",
    ]
    for comando in proibido:
        with _como_bi(bi_pronto, autocommit=True) as conn, pytest.raises(psycopg.Error):
            conn.execute(comando)

    # Mesmo desligando o modo somente leitura da própria sessão, não há privilégio de escrita.
    with _como_bi(bi_pronto, autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = off")
        assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "off"
        for comando in proibido[4:]:
            with pytest.raises(psycopg.Error):
                conn.execute(comando)


def test_nenhuma_view_traz_xml_credencial_ou_o_conteudo_do_documento(bi_pronto, empresas_com_dados):
    alfa, _ = empresas_com_dados
    with schema_context(alfa.schema_name):
        _nota()
    proibidas = re.compile(r"xml|senha|pfx|segredo|token|password|credencial|hash|sha256", re.I)
    with _como_bi(bi_pronto) as conn:
        colunas = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'bi'"
        ).fetchall()
        assert colunas and not [c for c in colunas if proibidas.search(c[1])], colunas
        for (tabela,) in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'bi'"
        ).fetchall():
            conteudo = conn.execute(
                f"SELECT coalesce(string_agg(t::text, ' '), '') FROM bi.{tabela} t"
            ).fetchone()[0]
            assert "conteudo-que-nao-pode-aparecer-no-bi" not in conteudo
            assert "<NFSe>" not in conteudo
            assert "smtp.exemplo.test" not in conteudo  # configuração de e-mail da empresa


def test_cpf_sai_mascarado_e_o_nome_da_pessoa_fisica_nao_sai(bi_pronto, empresas_com_dados):
    alfa, _ = empresas_com_dados
    with schema_context(alfa.schema_name):
        _nota(numero_nfse="10")  # tomador pessoa jurídica
        _nota(
            tomador={"tipo": "pf", "codigo_municipio": "2903201"},
            tomador_documento="12345678909",
            tomador_nome="MARIA DA SILVA",
            numero_nfse="11",
        )
    with _como_bi(bi_pronto) as conn:
        pf = conn.execute(
            "SELECT tomador_tipo, tomador_documento, tomador_nome FROM bi.notas "
            "WHERE numero_nfse = '11'"
        ).fetchone()
        pj = conn.execute(
            "SELECT tomador_tipo, tomador_documento, tomador_nome FROM bi.notas "
            "WHERE numero_nfse = '10'"
        ).fetchone()

    assert pf == ("pf", "***456789**", None)
    assert pj == ("pj", "11222333000262", "TOMADOR PJ LTDA")


def test_valores_saem_como_numeros_e_a_nota_substituida_como_referencia(
    bi_pronto, empresas_com_dados
):
    alfa, _ = empresas_com_dados
    with schema_context(alfa.schema_name):
        original = _nota(numero_nfse="20", situacao=Nfse.Situacao.SUBSTITUIDA)
        _nota(numero_nfse="21", substitui=original)
    with _como_bi(bi_pronto) as conn:
        linha = conn.execute(
            "SELECT nota_substituida_id, valor_servico, valor_iss, aliquota_iss, iss_retido "
            "FROM bi.notas WHERE numero_nfse = '21'"
        ).fetchone()

    assert linha == (original.pk, Decimal("1000.00"), Decimal("20.00"), Decimal("2.00"), False)


def test_servicos_prestados_uma_linha_por_nota_sem_a_descricao_livre(bi_pronto, empresas_com_dados):
    alfa, _ = empresas_com_dados
    with schema_context(alfa.schema_name):
        _nota(numero_nfse="30")
    with _como_bi(bi_pronto) as conn:
        linha = conn.execute(
            "SELECT servico_id, servico_nome, codigo_tributacao_nacional, s.valor_servico "
            "FROM bi.servicos s JOIN bi.notas n USING (nota_id, empresa_id) "
            "WHERE n.numero_nfse = '30'"
        ).fetchone()
        colunas = {
            c[0]
            for c in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'bi' AND table_name = 'servicos'"
            )
        }

    assert linha == (7, "Consultoria", "170101", Decimal("1000.00"))
    assert "descricao" not in colunas


def test_retencoes_uma_linha_por_nota_e_tipo_so_com_valor(bi_pronto, empresas_com_dados):
    alfa, _ = empresas_com_dados
    with schema_context(alfa.schema_name):
        _nota(
            numero_nfse="40",
            totais={
                "valor_iss": "20.00",
                "iss_retido": True,
                "retencao_irrf": "15.00",
                "retencao_csll": "0.00",
                "retencao_inss": "110.00",
            },
        )
        _nota(numero_nfse="41", totais={"valor_iss": "20.00", "iss_retido": False})
    with _como_bi(bi_pronto) as conn:
        linhas = conn.execute(
            "SELECT n.numero_nfse, r.tipo, r.valor FROM bi.retencoes r "
            "JOIN bi.notas n USING (nota_id, empresa_id) ORDER BY 1, 2"
        ).fetchall()

    assert linhas == [
        ("40", "inss", Decimal("110.00")),
        ("40", "irrf", Decimal("15.00")),
        ("40", "iss", Decimal("20.00")),
    ]  # nota 41: ISS não retido, nada retido; csll zerado não vira linha


def test_eventos_sem_o_xml(bi_pronto, empresas_com_dados):
    alfa, _ = empresas_com_dados
    with schema_context(alfa.schema_name):
        nota = _nota(numero_nfse="50")
        EventoNfse.objects.create(
            nfse=nota,
            tipo_evento="101101",
            identificador="1",
            descricao="Cancelamento",
            xml=b"<evento>sigiloso</evento>",
        )
    with _como_bi(bi_pronto) as conn:
        linha = conn.execute("SELECT nota_id, tipo_evento, descricao FROM bi.eventos").fetchone()

    assert linha == (nota.pk, "101101", "Cancelamento")


# -- manutenção das views ------------------------------------------------------------------------


def test_uma_empresa_nova_entra_nas_views_sozinha(bi_pronto, empresas_com_dados):
    nova = Empresa.objects.create(razao_social="Empresa Gama Teste Ltda", cnpj=CNPJ_C)
    try:
        with schema_context(nova.schema_name):
            _nota(numero_nfse="60")
        with _como_bi(bi_pronto) as conn:
            cnpjs = [r[0] for r in conn.execute("SELECT empresa_cnpj FROM bi.empresas ORDER BY 1")]
            gama = conn.execute(
                "SELECT count(*) FROM bi.notas WHERE empresa_cnpj = %s", [nova.cnpj]
            ).fetchone()[0]
        assert nova.cnpj in cnpjs and gama == 1
    finally:
        bi.atualizar_views()  # antes de a fixture apagar o schema
        nova.delete(force_drop=True)


def test_sem_o_schema_bi_criar_empresa_nao_cria_nada(empresas_com_dados, usuario_bi):
    assert not bi.esquema_existe()
    Empresa.objects.create(razao_social="Empresa Delta Teste Ltda", cnpj=CNPJ_C).delete(
        force_drop=True
    )

    assert not bi.esquema_existe()


def test_atualizar_e_idempotente(bi_pronto, empresas_com_dados):
    assert bi.atualizar_views() == 2
    assert bi.atualizar_views() == 2
    with _como_bi(bi_pronto) as conn:  # o SELECT do usuário sobrevive à recriação das views
        assert conn.execute("SELECT count(*) FROM bi.notas").fetchone()[0] == 3


def test_sem_nenhuma_empresa_as_views_existem_e_ficam_vazias_com_as_colunas_certas(
    bi_pronto, monkeypatch
):
    monkeypatch.setattr(bi, "_empresas", lambda: [])

    assert bi.atualizar_views() == 0

    with _como_bi(bi_pronto) as conn:
        for view in ("empresas", "notas", "servicos", "retencoes", "eventos"):
            assert conn.execute(f"SELECT count(*) FROM bi.{view}").fetchone()[0] == 0
        assert conn.execute("SELECT valor_iss FROM bi.notas").fetchall() == []


def test_o_comando_atualizar_respeita_se_existir(empresas_com_dados, usuario_bi):
    saida = io.StringIO()
    call_command("atualizar_views_bi", "--se-existir", stdout=saida)
    assert "nada a atualizar" in saida.getvalue() and not bi.esquema_existe()

    call_command("atualizar_views_bi", stdout=saida)
    assert bi.esquema_existe()


# -- o usuário de leitura ------------------------------------------------------------------------


def test_criar_usuario_bi_pelo_comando_nao_imprime_a_senha(
    empresas_com_dados, usuario_bi, monkeypatch
):
    monkeypatch.setenv("FREENFSE_BI_SENHA", SENHA)
    saida = io.StringIO()

    call_command("criar_usuario_bi", stdout=saida)

    assert SENHA not in saida.getvalue() and usuario_bi in saida.getvalue()
    with _como_bi(usuario_bi) as conn:  # a senha funciona (prova do verificador SCRAM)
        assert conn.execute("SELECT count(*) FROM bi.empresas").fetchone()[0] == 2


def test_criar_usuario_bi_exige_senha_forte(empresas_com_dados, usuario_bi, monkeypatch):
    monkeypatch.delenv("FREENFSE_BI_SENHA", raising=False)
    with pytest.raises(CommandError, match="Informe a senha"):
        call_command("criar_usuario_bi", stdout=io.StringIO())

    monkeypatch.setenv("FREENFSE_BI_SENHA", "curta")
    with pytest.raises(CommandError, match="pelo menos 16"):
        call_command("criar_usuario_bi", stdout=io.StringIO())


def test_senha_pelo_arquivo(empresas_com_dados, usuario_bi, tmp_path):
    arquivo = tmp_path / "bi.senha"
    arquivo.write_text(SENHA + "\n")

    call_command("criar_usuario_bi", f"--senha-arquivo={arquivo}", stdout=io.StringIO())

    with _como_bi(usuario_bi) as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)


def test_o_verificador_scram_tem_o_formato_do_postgresql():
    verificador = bi.verificador_scram("qualquer-senha-longa-123")

    assert re.fullmatch(
        r"SCRAM-SHA-256\$4096:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+", verificador
    )
    assert "qualquer-senha" not in verificador
    assert verificador != bi.verificador_scram("qualquer-senha-longa-123")  # sal aleatório


def test_o_usuario_de_leitura_nao_e_super_nem_cria_nada(bi_pronto):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolcanlogin "
            "FROM pg_roles WHERE rolname = %s",
            [bi_pronto],
        )
        assert cursor.fetchone() == (False, False, False, False, True)
