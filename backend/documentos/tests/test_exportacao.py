"""Download em lote: ZIP com XML, PDF e CSV; limites, progresso, expurgo, acesso e nomes seguros."""

import csv
import datetime as dt
import io
import zipfile

import pytest
from django_tenants.utils import schema_context

from core.models import LogAuditoria, Usuario
from core.permissoes import Perfil
from documentos import tasks
from documentos.models import Exportacao
from documentos.services import contexto, exportacao
from documentos.tests.apoio import emitir, nota_avulsa
from fiscal.models import Nfse
from fiscal.services import emissao

pytestmark = pytest.mark.django_db
S = Exportacao.Situacao


def _pedir(usuario, **filtros):
    return exportacao.solicitar(filtros, usuario=usuario)


def _zip(pedido):
    pedido.refresh_from_db()
    return zipfile.ZipFile(exportacao.pasta_da_empresa() / pedido.arquivo)


def _linhas(arquivo_zip):
    texto = arquivo_zip.read("resumo.csv").decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


@pytest.fixture
def dono(db):
    return Usuario.objects.create_user(email="dono@exemplo.test", password="x" * 14, nome="Dono")


# -- conteúdo ------------------------------------------------------------------------------


def test_o_zip_tem_o_xml_o_pdf_e_o_csv_de_cada_nota(empresa_pronta, nova_nota, sefin, dono):
    primeira = emitir(empresa_pronta, nova_nota, valor="1500.00")
    segunda = emitir(empresa_pronta, nova_nota, valor="250.50")
    pedido = _pedir(dono)

    assert exportacao.gerar(pedido.pk) == "pronta"

    arquivo = _zip(pedido)
    nomes = sorted(arquivo.namelist())
    assert nomes[0].startswith("pdf/") and "resumo.csv" in nomes
    assert len([n for n in nomes if n.startswith("xml/")]) == 2
    assert len([n for n in nomes if n.startswith("pdf/")]) == 2
    xml = arquivo.read(next(n for n in nomes if n.startswith("xml/") and "NFSe 1" in n))
    assert xml == bytes(primeira.xml_nfse)
    assert arquivo.read(next(n for n in nomes if n.startswith("pdf/"))).startswith(b"%PDF")
    linhas = _linhas(arquivo)
    assert [linha["numero_nfse"] for linha in linhas] == ["1", "2"]
    assert linhas[0]["valor_servico"] == "1500,00" and linhas[1]["valor_servico"] == "250,50"
    assert linhas[0]["chave"] == primeira.chave and linhas[1]["chave"] == segunda.chave
    assert linhas[0]["situacao"] == "Autorizada" and linhas[0]["competencia"] == "10/2026"
    assert linhas[0]["data_emissao"] == "2026-11-02" and linhas[0]["valor_iss"] == "30,00"
    assert {linha["arquivo_xml"] for linha in linhas} <= set(nomes)
    assert not any(linha["observacao"] for linha in linhas)
    assert zipfile.ZipFile(exportacao.pasta_da_empresa() / pedido.arquivo).testzip() is None


def test_o_csv_abre_no_excel_brasileiro(empresa_pronta, nova_nota, sefin, dono):
    emitir(empresa_pronta, nova_nota)
    pedido = _pedir(dono)
    exportacao.gerar(pedido.pk)

    bruto = _zip(pedido).read("resumo.csv")

    assert bruto.startswith(b"\xef\xbb\xbf")  # BOM do Excel
    assert b";" in bruto.splitlines()[0] and b"\r\n" in bruto


def test_nota_cancelada_vai_com_o_xml_e_a_situacao_certa(empresa_pronta, nova_nota, sefin, dono):
    nota = emitir(empresa_pronta, nova_nota)
    emissao.cancelar(
        empresa_pronta,
        nota,
        codigo_motivo=1,
        justificativa="Nota emitida com valor errado.",
        usuario=None,
    )
    pedido = _pedir(dono)

    exportacao.gerar(pedido.pk)

    linha = _linhas(_zip(pedido))[0]
    assert linha["situacao"] == "Cancelada" and linha["arquivo_pdf"].startswith("pdf/")


def test_rascunho_e_nota_sem_xml_nao_entram(empresa_pronta, nova_nota, sefin, dono):
    emitir(empresa_pronta, nova_nota)
    nova_nota()  # rascunho

    pedido = _pedir(dono)

    assert pedido.total == 1


# -- filtros -------------------------------------------------------------------------------


def test_os_filtros_de_periodo_competencia_situacao_e_tomador(empresa_ativa, dono):
    nova = nota_avulsa(
        1, emitida_em=dt.datetime(2026, 11, 20, 15, tzinfo=dt.UTC), tomador_nome="ALFA SA"
    )
    velha = nota_avulsa(
        2, emitida_em=dt.datetime(2026, 10, 5, 15, tzinfo=dt.UTC), competencia=dt.date(2026, 9, 1),
        tomador_nome="BETA LTDA", tomador_documento="99888777000166",
    )  # fmt: skip
    cancelada = nota_avulsa(3, situacao=Nfse.Situacao.CANCELADA, tomador_nome="GAMA ME")

    def total(**filtros):
        return exportacao.filtrar_notas(filtros).count()

    assert total() == 3
    assert total(periodo_inicio="2026-11-01") == 2 and total(periodo_fim="2026-10-31") == 1
    assert total(competencia="2026-09") == 1 and total(competencia="2026-10") == 2
    assert total(situacao=["cancelada"]) == 1 and total(situacao=["autorizada"]) == 2
    assert total(tomador="beta") == 1 and total(tomador="99.888.777") == 1
    assert {nova, velha, cancelada} == set(exportacao.filtrar_notas({}))


# -- limites e progresso -------------------------------------------------------------------


def test_limite_de_quantidade_recusa_o_pedido_sem_gerar_nada(empresa_ativa, dono, settings):
    settings.FREENFSE_LOTE_MAX_NOTAS = 2
    for n in range(1, 4):
        nota_avulsa(n)

    with pytest.raises(exportacao.ErroDeExportacao, match="3 notas e o limite de um lote é 2"):
        _pedir(dono)

    assert Exportacao.objects.count() == 0


def test_lote_sem_notas_e_recusado(empresa_ativa, dono):
    with pytest.raises(exportacao.ErroDeExportacao, match="Nenhuma nota encontrada"):
        _pedir(dono, tomador="ninguém")


def test_limite_de_tamanho_interrompe_o_lote_e_nao_deixa_arquivo(
    empresa_pronta, nova_nota, sefin, dono, settings
):
    emitir(empresa_pronta, nova_nota)
    pedido = _pedir(dono)
    settings.FREENFSE_LOTE_MAX_MB = 0  # qualquer conteúdo passa do limite

    assert exportacao.gerar(pedido.pk) == "falhou"

    pedido.refresh_from_db()
    assert "passou de 0 MB" in pedido.erro and pedido.arquivo == ""
    assert list(exportacao.pasta_da_empresa().glob("*.zip")) == []


def test_o_progresso_acompanha_as_notas_processadas(empresa_pronta, nova_nota, sefin, dono):
    emitir(empresa_pronta, nova_nota)
    emitir(empresa_pronta, nova_nota)
    pedido = _pedir(dono)
    assert (pedido.situacao, pedido.total, pedido.processadas) == ("pendente", 2, 0)

    exportacao.gerar(pedido.pk)

    pedido.refresh_from_db()
    assert (pedido.situacao, pedido.processadas, pedido.total) == ("pronta", 2, 2)
    assert pedido.tamanho_bytes > 0 and pedido.expira_em > pedido.concluido_em


def test_gerar_duas_vezes_nao_refaz_o_arquivo(empresa_pronta, nova_nota, sefin, dono):
    emitir(empresa_pronta, nova_nota)
    pedido = _pedir(dono)
    exportacao.gerar(pedido.pk)
    pedido.refresh_from_db()
    arquivo = pedido.arquivo

    exportacao.gerar(pedido.pk)  # reentrega da tarefa

    pedido.refresh_from_db()
    assert pedido.arquivo == arquivo and len(list(exportacao.pasta_da_empresa().glob("*.zip"))) == 1


def test_pdf_indisponivel_nao_derruba_o_lote(empresa_pronta, nova_nota, sefin, dono, monkeypatch):
    emitir(empresa_pronta, nova_nota)
    pedido = _pedir(dono)

    def sem_pdf(empresa, nfse):
        raise emissao.ErroDeEmissao("A Sefin não respondeu.")

    monkeypatch.setattr(emissao, "gerar_danfse", sem_pdf)
    exportacao.gerar(pedido.pk)

    pedido.refresh_from_db()
    arquivo = _zip(pedido)
    assert pedido.situacao == "pronta" and not [
        n for n in arquivo.namelist() if n.startswith("pdf/")
    ]
    assert "PDF indisponível" in _linhas(arquivo)[0]["observacao"]
    assert pedido.avisos and "PDF indisponível" in pedido.avisos[0]


# -- nomes maliciosos ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome",
    [
        "../../etc/passwd",
        "C:\\Windows\\System32\\x",
        "a/b\\c\x00d\x1f.xml",
        "..",
        "....//....//",
        '<script>alert("x")</script>',
        "",
        "CON",
    ],
)
def test_nome_seguro_nunca_tem_separador_controle_nem_ponto_duplo(nome):
    seguro = exportacao.nome_seguro(nome)

    assert seguro and "/" not in seguro and "\\" not in seguro and ".." not in seguro
    assert not any(ord(c) < 32 or ord(c) == 127 for c in seguro)
    assert not seguro.startswith(".") and len(seguro) <= 80


def test_tomador_malicioso_nao_escapa_do_zip_nem_vira_formula(
    empresa_pronta, nova_nota, sefin, dono
):
    primeira = emitir(empresa_pronta, nova_nota)
    segunda = emitir(empresa_pronta, nova_nota)
    Nfse.objects.filter(pk=primeira.pk).update(tomador_nome="../../../etc/passwd\x1f")
    Nfse.objects.filter(pk=segunda.pk).update(tomador_nome="=cmd|' /C calc'!A0 \\..\\..\\x")
    pedido = _pedir(dono)

    exportacao.gerar(pedido.pk)

    arquivo = _zip(pedido)
    for nome in arquivo.namelist():
        assert (
            not nome.startswith("/")
            and ".." not in nome
            and "\\" not in nome
            and "\x00" not in nome
        )
        assert nome.count("/") <= 1  # só xml/ ou pdf/
    assert len(set(n.lower() for n in arquivo.namelist())) == len(arquivo.namelist())
    texto = arquivo.read("resumo.csv").decode("utf-8-sig")
    assert "'=cmd" in texto and ";=cmd" not in texto  # a fórmula foi neutralizada


@pytest.mark.parametrize("valor", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"])
def test_celulas_que_comecam_como_formula_levam_apostrofo(valor):
    assert exportacao._celula(valor) == "'" + valor
    assert exportacao._celula("normal") == "normal" and exportacao._celula(None) == ""


def test_nomes_repetidos_dentro_do_zip_ganham_sufixo(empresa_pronta, nova_nota, sefin, dono):
    primeira = emitir(empresa_pronta, nova_nota)
    segunda = emitir(empresa_pronta, nova_nota)
    Nfse.objects.filter(pk__in=[primeira.pk, segunda.pk]).update(
        numero_nfse="9", tomador_nome="IGUAL"
    )
    pedido = _pedir(dono)

    exportacao.gerar(pedido.pk)

    nomes = [n for n in _zip(pedido).namelist() if n.startswith("xml/")]
    assert sorted(nomes) == ["xml/NFSe 9 - IGUAL (2).xml", "xml/NFSe 9 - IGUAL.xml"]


# -- expurgo -------------------------------------------------------------------------------


def test_o_expurgo_apaga_o_zip_vencido_e_marca_o_pedido(empresa_pronta, nova_nota, sefin, dono):
    emitir(empresa_pronta, nova_nota)
    pedido = _pedir(dono)
    exportacao.gerar(pedido.pk)
    pedido.refresh_from_db()
    arquivo = exportacao.pasta_da_empresa() / pedido.arquivo

    assert (
        exportacao.expurgar(agora=pedido.expira_em - dt.timedelta(minutes=1)) == 0
        and arquivo.exists()
    )
    assert exportacao.expurgar(agora=pedido.expira_em + dt.timedelta(minutes=1)) == 1

    pedido.refresh_from_db()
    assert not arquivo.exists() and (pedido.situacao, pedido.arquivo) == ("expirada", "")
    with pytest.raises(exportacao.ErroDeExportacao):
        exportacao.abrir_para_download(pedido, dono)


def test_o_expurgo_apaga_arquivo_orfao_antigo_mas_preserva_o_recente(empresa_ativa):
    import os

    pasta = exportacao.pasta_da_empresa()
    antigo, recente = pasta / "antigo.zip", pasta / "recente.zip"
    antigo.write_bytes(b"x")
    recente.write_bytes(b"x")
    velho = (contexto.agora() - dt.timedelta(days=3)).timestamp()
    os.utime(antigo, (velho, velho))

    assert exportacao.expurgar() == 1

    assert not antigo.exists() and recente.exists()


def test_a_tarefa_periodica_de_expurgo_passa_por_todas_as_empresas(empresa_a, empresa_b):
    for empresa in (empresa_a, empresa_b):
        with schema_context(empresa.schema_name):
            pasta = exportacao.pasta_da_empresa()
            arquivo = pasta / "velho.zip"
            arquivo.write_bytes(b"x")
            import os

            velho = (contexto.agora() - dt.timedelta(days=3)).timestamp()
            os.utime(arquivo, (velho, velho))

    assert tasks.expurgar_exportacoes() == 2


# -- download e acesso ---------------------------------------------------------------------


def test_so_quem_pediu_baixa_e_a_baixa_e_auditada(empresa_pronta, nova_nota, sefin, dono):
    emitir(empresa_pronta, nova_nota)
    outro = Usuario.objects.create_user(email="outro@exemplo.test", password="x" * 14, nome="Outro")
    pedido = _pedir(dono)
    exportacao.gerar(pedido.pk)
    pedido.refresh_from_db()

    with pytest.raises(exportacao.ErroDeExportacao, match="outra pessoa"):
        exportacao.abrir_para_download(pedido, outro)
    caminho = exportacao.abrir_para_download(pedido, dono)

    assert caminho.is_file()
    acoes = list(LogAuditoria.objects.values_list("acao", flat=True))
    assert "exportacao_solicitada" in acoes and "exportacao_baixada" in acoes
    pedido.refresh_from_db()
    assert pedido.baixado_em is not None


def test_download_antes_de_pronto_ou_depois_de_expirar_e_recusado(
    empresa_pronta, nova_nota, sefin, dono
):
    emitir(empresa_pronta, nova_nota)
    pedido = _pedir(dono)
    with pytest.raises(exportacao.ErroDeExportacao, match="ainda não está pronto"):
        exportacao.abrir_para_download(pedido, dono)

    exportacao.gerar(pedido.pk)
    pedido.refresh_from_db()
    with pytest.raises(exportacao.ErroDeExportacao, match="expirou"):
        exportacao.abrir_para_download(
            pedido, dono, agora=pedido.expira_em + dt.timedelta(seconds=1)
        )


def test_cada_empresa_tem_a_propria_pasta_de_arquivos(empresa_a, empresa_b):
    with schema_context(empresa_a.schema_name):
        pasta_a = exportacao.pasta_da_empresa()
    with schema_context(empresa_b.schema_name):
        pasta_b = exportacao.pasta_da_empresa()

    assert pasta_a != pasta_b and pasta_a.name == empresa_a.schema_name
    assert oct(pasta_a.stat().st_mode & 0o777) == "0o700"


def test_a_tarefa_gera_o_arquivo_no_schema_da_empresa(empresa_pronta, nova_nota, sefin, dono):
    emitir(empresa_pronta, nova_nota)
    pedido = _pedir(dono)

    assert tasks.gerar_exportacao(empresa_pronta.schema_name, pedido.pk) == "pronta"
    assert Perfil.EMISSOR  # as permissões do download são testadas na API
