"""Cópia ao Google Drive (simulado): configuração, pastas, nomes, fileId, eventos e retentativa."""

import datetime as dt

import pytest
from django.core.exceptions import ObjectDoesNotExist  # noqa: F401
from django_tenants.utils import schema_context

from core.models import LogAuditoria
from documentos import tasks
from documentos.models import ArquivoDrive, ConfiguracaoDrive, PastaDrive
from documentos.services import contexto
from documentos.services.drive import envio
from documentos.services.drive.cliente import ErroDrive
from documentos.tests.apoio import ativar_drive, emitir, nota_avulsa
from documentos.tests.simulados import DriveSimulado, conta_de_servico_json
from fiscal.services import emissao

pytestmark = pytest.mark.django_db
CHAVE_RAW = "SELECT conta_servico FROM documentos_configuracaodrive"


@pytest.fixture
def drive():
    return DriveSimulado()


@pytest.fixture
def trocas(drive):
    return {"cliente": lambda _configuracao: drive}


def _nomes(drive):
    return sorted(drive.caminho_de(a["id"]) for a in drive.arquivos())


# -- configuração --------------------------------------------------------------------------


def _salvar(trocas, **dados):
    base = {
        "ativo": True,
        "conta_servico": conta_de_servico_json("conta@projeto-ficticio.iam.gserviceaccount.com"),
        "pasta_raiz_id": "RAIZ",
        "modelo_subpastas": "{ano}/{mes}",
        "modelo_arquivo": "{chave}",
    }
    base.update(dados)
    return envio.salvar_configuracao(dados=base, usuario=None, trocas=trocas)


def test_salvar_valida_a_pasta_raiz_e_guarda_o_nome_e_o_email_da_conta(empresa_ativa, trocas):
    configuracao = _salvar(trocas)

    assert configuracao.pasta_raiz_nome == "Notas Fiscais"
    assert configuracao.conta_servico_email == "conta@projeto-ficticio.iam.gserviceaccount.com"
    assert configuracao.validado_em is not None
    assert "nfse" not in str(configuracao).lower()


def test_a_credencial_fica_cifrada_na_coluna(empresa_ativa, trocas):
    from django.db import connection

    _salvar(trocas)

    with connection.cursor() as cursor:
        cursor.execute(CHAVE_RAW)
        bruto = cursor.fetchone()[0]
    assert "private_key" not in bruto and "BEGIN PRIVATE KEY" not in bruto
    assert ConfiguracaoDrive.obter().conta_servico.startswith("{")  # o modelo decifra


@pytest.mark.parametrize(
    ("ajuste", "campo", "trecho"),
    [
        ({"pasta_raiz_id": "NAO-EXISTE"}, "pasta_raiz_id", "não encontrou a pasta"),
        ({"pasta_raiz_id": ""}, "pasta_raiz_id", "Informe o ID da pasta raiz"),
        ({"conta_servico": "isto não é json"}, "conta_servico", "não é um JSON válido"),
        (
            {"conta_servico": '{"type": "authorized_user"}'},
            "conta_servico",
            "não é de uma conta de serviço",
        ),
        ({"modelo_arquivo": "{x}"}, "modelo_arquivo", "{x} não existe"),
    ],
)
def test_erros_da_configuracao(empresa_ativa, trocas, ajuste, campo, trecho):
    with pytest.raises(envio.ErroDeConfiguracaoDrive) as erro:
        _salvar(trocas, **ajuste)

    assert trecho in " ".join(erro.value.erros[campo])


def test_pasta_sem_permissao_de_escrita_diz_com_quem_compartilhar(empresa_ativa):
    drive = DriveSimulado(pode_escrever=False)

    with pytest.raises(envio.ErroDeConfiguracaoDrive) as erro:
        _salvar({"cliente": lambda _c: drive})

    assert "conta@projeto-ficticio.iam.gserviceaccount.com" in erro.value.erros["pasta_raiz_id"][0]
    assert "Editor" in erro.value.erros["pasta_raiz_id"][0]


def test_id_de_arquivo_no_lugar_de_pasta_e_recusado(empresa_ativa, trocas, drive):
    arquivo_id = drive.enviar("a.txt", "RAIZ", b"x", "text/plain")

    with pytest.raises(envio.ErroDeConfiguracaoDrive) as erro:
        _salvar(trocas, pasta_raiz_id=arquivo_id)

    assert "não de uma pasta" in erro.value.erros["pasta_raiz_id"][0]


def test_todos_os_erros_de_modelo_vem_juntos_e_nada_e_gravado(empresa_ativa, trocas):
    with pytest.raises(envio.ErroDeConfiguracaoDrive) as erro:
        _salvar(trocas, modelo_subpastas="{ano}//{x}", modelo_arquivo="{y")

    assert {"modelo_subpastas", "modelo_arquivo"} <= set(erro.value.erros)
    assert not ConfiguracaoDrive.obter().ativo


def test_a_alteracao_da_configuracao_e_auditada_sem_a_credencial(empresa_ativa, trocas):
    _salvar(trocas)

    registro = LogAuditoria.objects.get(acao="drive_config_alterada")
    assert "private_key" not in str(registro.detalhes) and "BEGIN" not in str(registro.detalhes)


# -- cópia da nota -------------------------------------------------------------------------


def test_nota_autorizada_vai_ao_drive_na_pasta_e_no_nome_do_modelo(
    empresa_pronta, nova_nota, sefin, drive, trocas
):
    ativar_drive(
        modelo_subpastas="{ano}/{mes}/{cnpj_emitente}",
        modelo_arquivo="NFSe {numero_nfse} - {chave}",
    )
    nota = emitir(empresa_pronta, nova_nota)

    resultado = envio.enviar_nota(nota, trocas=trocas)

    assert resultado == {"xml": "enviado", "pdf": "enviado"}
    base = f"2026/11/{empresa_pronta.cnpj}/NFSe 1 - {nota.chave}"
    assert _nomes(drive) == [f"{base}.pdf", f"{base}.xml"]
    xml = next(a for a in drive.arquivos() if a["nome"].endswith(".xml"))
    assert xml["conteudo"] == bytes(nota.xml_nfse)
    pdf = next(a for a in drive.arquivos() if a["nome"].endswith(".pdf"))
    assert pdf["conteudo"].startswith(b"%PDF")
    assert {a.situacao for a in nota.arquivos_drive.all()} == {"enviado"}


def test_reenviar_sobrescreve_pelo_file_id_e_nao_duplica(
    empresa_pronta, nova_nota, sefin, drive, trocas
):
    ativar_drive()
    nota = emitir(empresa_pronta, nova_nota)
    envio.enviar_nota(nota, trocas=trocas)
    ids = {a.papel: a.file_id for a in nota.arquivos_drive.all()}
    antes = len(drive.arquivos())

    envio.reenviar(nota, usuario=None, trocas=trocas)

    assert len(drive.arquivos()) == antes
    assert {a.papel: a.file_id for a in nota.arquivos_drive.all()} == ids
    assert [c for c in drive.chamadas if c[0] == "atualizar"]
    assert "drive_reenviado" in set(LogAuditoria.objects.values_list("acao", flat=True))


def test_as_pastas_sao_criadas_uma_vez_e_ficam_no_cache(
    empresa_pronta, nova_nota, sefin, drive, trocas
):
    ativar_drive(modelo_subpastas="{ano}/{mes}")
    primeira = emitir(empresa_pronta, nova_nota)
    segunda = emitir(empresa_pronta, nova_nota, valor="50.00")

    envio.enviar_nota(primeira, trocas=trocas)
    envio.enviar_nota(segunda, trocas=trocas)

    assert [p["nome"] for p in drive.pastas()] == ["2026", "11"]
    assert list(PastaDrive.objects.order_by("caminho").values_list("caminho", flat=True)) == [
        "2026",
        "2026/11",
    ]
    assert len([c for c in drive.chamadas if c[0] == "criar_pasta"]) == 2


def test_nome_repetido_de_outra_nota_recebe_sufixo_e_aviso(empresa_ativa, drive, trocas):
    ativar_drive(modelo_subpastas="{ano}", modelo_arquivo="NFSe {numero_nfse} - {cnpj_emitente}")
    primeira = nota_avulsa(5, chave="1" * 50)
    segunda = nota_avulsa(5, chave="2" * 50)  # mesmo número e mesmo CNPJ → mesmo nome

    envio.enviar_nota(primeira, trocas=trocas, papeis=("xml",))
    envio.enviar_nota(segunda, trocas=trocas, papeis=("xml",))

    cnpj = empresa_ativa.cnpj
    assert _nomes(drive) == [f"2026/NFSe 5 - {cnpj} (2).xml", f"2026/NFSe 5 - {cnpj}.xml"]
    xml_da_segunda = segunda.arquivos_drive.get(papel="xml")
    assert "outra nota" in xml_da_segunda.aviso and "(2)" in xml_da_segunda.aviso
    assert primeira.arquivos_drive.get(papel="xml").aviso == ""


def test_arquivo_de_terceiro_com_o_mesmo_nome_tambem_leva_sufixo(empresa_ativa, drive, trocas):
    ativar_drive(modelo_subpastas="", modelo_arquivo="{cnpj_emitente} {numero_nfse}")
    nota = nota_avulsa(9)
    drive.enviar(f"{empresa_ativa.cnpj} 9.xml", "RAIZ", b"de outra pessoa", "application/xml")

    envio.enviar_nota(nota, trocas=trocas, papeis=("xml",))

    assert f"{empresa_ativa.cnpj} 9 (2).xml" in {a["nome"] for a in drive.arquivos()}


def test_arquivo_proprio_gravado_antes_da_queda_e_reaproveitado(empresa_ativa, drive, trocas):
    ativar_drive()
    nota = nota_avulsa(3)
    envio.enviar_nota(nota, trocas=trocas, papeis=("xml",))
    linha = nota.arquivos_drive.get(papel="xml")
    id_original = linha.file_id
    ArquivoDrive.objects.filter(pk=linha.pk).update(
        file_id="", situacao="pendente", nome="", pasta_id=""
    )

    envio.enviar_nota(
        nota, trocas=trocas, papeis=("xml",), agora=contexto.agora() + dt.timedelta(hours=1)
    )

    assert len(drive.arquivos()) == 1  # não criou " (2)": reconheceu o arquivo pelas propriedades
    assert nota.arquivos_drive.get(papel="xml").file_id == id_original


def test_pasta_apagada_no_drive_e_recriada_e_o_cache_se_corrige(empresa_ativa, drive, trocas):
    ativar_drive(modelo_subpastas="{ano}")
    primeira = nota_avulsa(1)
    envio.enviar_nota(primeira, trocas=trocas, papeis=("xml",))
    pasta_antiga = PastaDrive.objects.get().pasta_id
    del drive.itens[pasta_antiga]  # o usuário apagou a pasta no Drive

    segunda = nota_avulsa(2)
    envio.enviar_nota(segunda, trocas=trocas, papeis=("xml",))

    assert PastaDrive.objects.get().pasta_id != pasta_antiga
    assert segunda.arquivos_drive.get(papel="xml").situacao == "enviado"


def test_arquivo_apagado_no_drive_e_recriado_ao_reenviar(empresa_ativa, drive, trocas):
    ativar_drive()
    nota = nota_avulsa(1)
    envio.enviar_nota(nota, trocas=trocas, papeis=("xml",))
    antigo = nota.arquivos_drive.get(papel="xml").file_id
    del drive.itens[antigo]

    envio.enviar_nota(nota, trocas=trocas, papeis=("xml",), forcar=True)

    novo = nota.arquivos_drive.get(papel="xml").file_id
    assert novo != antigo and novo in drive.itens


def test_drive_desligado_nao_copia_nada(empresa_ativa, drive, trocas):
    ativar_drive(ativo=False)

    assert envio.enviar_nota(nota_avulsa(1), trocas=trocas) == {}
    assert drive.arquivos() == []


# -- eventos -------------------------------------------------------------------------------


def test_cancelamento_grava_o_xml_do_evento_e_troca_o_pdf(
    empresa_pronta, nova_nota, sefin, drive, trocas
):
    ativar_drive()
    nota = emitir(empresa_pronta, nova_nota)
    envio.enviar_nota(nota, trocas=trocas)
    pdf_antes = next(a for a in drive.arquivos() if a["nome"].endswith(".pdf"))
    id_do_pdf, conteudo_antes = pdf_antes["id"], pdf_antes["conteudo"]

    emissao.cancelar(
        empresa_pronta,
        nota,
        codigo_motivo=1,
        justificativa="Nota emitida com valor errado.",
        usuario=None,
    )
    nota.refresh_from_db()
    evento = nota.eventos.get(tipo_evento="101101")
    envio.enviar_evento(nota, evento, trocas=trocas)

    nomes = _nomes(drive)
    assert len(nomes) == 3 and any(n.endswith("_cancelamento.xml") for n in nomes)
    evento_xml = next(a for a in drive.arquivos() if a["nome"].endswith("_cancelamento.xml"))
    assert evento_xml["conteudo"] == bytes(evento.xml)
    pdf_depois = drive.itens[id_do_pdf]  # o MESMO arquivo foi sobrescrito
    assert pdf_depois["conteudo"].startswith(b"%PDF") and pdf_depois["conteudo"] != conteudo_antes
    assert nota.arquivos_drive.get(papel="pdf").file_id == id_do_pdf


# -- retentativa ---------------------------------------------------------------------------


def test_falha_temporaria_reagenda_com_espera_e_depois_envia(empresa_ativa, drive, trocas):
    ativar_drive()
    nota = nota_avulsa(1)
    agora = contexto.agora()
    drive.falhas = [ErroDrive("Drive fora do ar.", detalhe="HTTP 503")]

    envio.enviar_nota(nota, trocas=trocas, papeis=("xml",), agora=agora)

    linha = nota.arquivos_drive.get(papel="xml")
    assert (linha.situacao, linha.tentativas) == ("pendente", 1)
    assert linha.proxima_tentativa == agora + dt.timedelta(minutes=1)
    assert envio.pendentes_vencidos(agora) == []
    assert envio.pendentes_vencidos(agora + dt.timedelta(minutes=2)) == [nota.pk]

    envio.enviar_nota(nota, trocas=trocas, papeis=("xml",), agora=agora + dt.timedelta(minutes=2))

    assert nota.arquivos_drive.get(papel="xml").situacao == "enviado"


def test_falha_permanente_nao_tenta_de_novo_e_explica(empresa_ativa, drive, trocas):
    ativar_drive()
    nota = nota_avulsa(1)
    drive.falhas = [ErroDrive("Compartilhe a pasta com a conta de serviço.", temporario=False)]

    envio.enviar_nota(nota, trocas=trocas, papeis=("xml",))

    linha = nota.arquivos_drive.get(papel="xml")
    assert (linha.situacao, linha.proxima_tentativa) == ("falhou", None)
    assert "Compartilhe a pasta" in linha.erro
    assert envio.pendentes_vencidos(contexto.agora() + dt.timedelta(days=1)) == []


def test_depois_de_cinco_falhas_temporarias_desiste(empresa_ativa, drive, trocas):
    ativar_drive()
    nota = nota_avulsa(1)
    agora = contexto.agora()
    for tentativa in range(5):
        drive.falhas = [ErroDrive("Drive fora do ar.")]
        envio.enviar_nota(
            nota, trocas=trocas, papeis=("xml",), agora=agora + dt.timedelta(days=tentativa)
        )

    assert nota.arquivos_drive.get(papel="xml").situacao == "falhou"


def test_a_rotina_periodica_enfileira_so_o_que_ja_venceu(
    empresa_ativa, drive, trocas, fila, monkeypatch
):
    ativar_drive()
    vencida, futura = nota_avulsa(1), nota_avulsa(2)
    agora = contexto.agora()
    ArquivoDrive.objects.create(
        nfse=vencida, papel="xml", proxima_tentativa=agora - dt.timedelta(minutes=1)
    )
    ArquivoDrive.objects.create(
        nfse=futura, papel="xml", proxima_tentativa=agora + dt.timedelta(hours=1)
    )
    monkeypatch.setattr(
        tasks.enviar_nota_ao_drive, "delay", lambda *a: fila.chamadas.append(("drive", a))
    )

    resultado = tasks.despachar_pendentes()

    assert resultado["notas_drive"] == 1
    assert fila.chamadas == [("drive", (empresa_ativa.schema_name, vencida.pk))]


# -- período e isolamento ------------------------------------------------------------------


def test_notas_do_periodo_usam_a_data_de_emissao(empresa_ativa):
    nova = nota_avulsa(1, emitida_em=dt.datetime(2026, 11, 20, 15, tzinfo=dt.UTC))
    velha = nota_avulsa(2, emitida_em=dt.datetime(2026, 10, 5, 15, tzinfo=dt.UTC))
    rascunho = nota_avulsa(3, situacao="rascunho")

    assert list(envio.notas_do_periodo(dt.date(2026, 11, 1), dt.date(2026, 11, 30))) == [nova]
    assert list(envio.notas_do_periodo(dt.date(2026, 10, 1), None)) == [velha, nova]
    assert rascunho not in envio.notas_do_periodo()


def test_cada_empresa_tem_o_proprio_cache_de_pastas_e_configuracao(
    empresa_a, empresa_b, drive, trocas
):
    with schema_context(empresa_a.schema_name):
        ativar_drive(modelo_subpastas="{ano}")
        envio.enviar_nota(nota_avulsa(1), trocas=trocas, papeis=("xml",))
        assert PastaDrive.objects.count() == 1
    with schema_context(empresa_b.schema_name):
        assert PastaDrive.objects.count() == 0 and ArquivoDrive.objects.count() == 0
        assert not ConfiguracaoDrive.obter().ativo
        assert envio.enviar_nota(nota_avulsa(1), trocas=trocas) == {}  # Drive desligado em B
