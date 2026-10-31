"""Download em lote: ZIP com o XML e o PDF das notas e uma planilha-resumo (CSV).

O ZIP é gerado em segundo plano numa pasta temporária (`FREENFSE_EXPORTACOES_DIR`, por empresa), com
limite de quantidade e de tamanho, e **expurgado** depois da retenção. Só quem pediu, e ainda tem
vínculo com a empresa, baixa o arquivo. Os nomes dentro do ZIP nunca vêm crus do cadastro: passam
por `nome_seguro` (sem barras, `..`, controle) e a planilha neutraliza fórmulas (CSV injection).
"""

import csv
import datetime as dt
import io
import logging
import re
import secrets
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.models import Q

from core.models import LogAuditoria
from core.services import auditoria
from documentos.models import Exportacao
from documentos.services import contexto
from fiscal.models import Nfse
from fiscal.services import emissao

logger = logging.getLogger(__name__)

S = Exportacao.Situacao
SITUACOES_EXPORTAVEIS = (
    Nfse.Situacao.AUTORIZADA,
    Nfse.Situacao.CANCELADA,
    Nfse.Situacao.SUBSTITUIDA,
)
COLUNAS = (
    "numero_nfse", "chave", "serie_dps", "numero_dps", "situacao", "competencia", "data_emissao",
    "tomador_nome", "tomador_documento", "valor_servico", "base_calculo", "valor_iss",
    "total_retencoes", "valor_liquido", "ambiente", "arquivo_xml", "arquivo_pdf", "observacao",
)  # fmt: skip
_PROIBIDOS = re.compile(r"[^\w\s.\-]", re.UNICODE)
_ESPACOS = re.compile(r"\s+")


class ErroDeExportacao(Exception):
    """Pedido de lote recusado ou impossível; a mensagem é para o usuário."""


def limite_de_notas():
    """Máximo de notas por lote."""
    return int(settings.FREENFSE_LOTE_MAX_NOTAS)


def limite_de_bytes():
    """Máximo de bytes (sem compactar) por lote."""
    return int(settings.FREENFSE_LOTE_MAX_MB) * 1024 * 1024


def retencao():
    """Quanto tempo o ZIP pronto fica disponível."""
    return dt.timedelta(hours=int(settings.FREENFSE_LOTE_RETENCAO_HORAS))


def pasta_da_empresa():
    """Pasta temporária dos ZIPs da empresa ativa (criada com acesso só do dono)."""
    pasta = Path(settings.FREENFSE_EXPORTACOES_DIR) / connection.schema_name
    pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
    return pasta


def nome_seguro(texto, padrao="arquivo", maximo=80):
    """Nome de arquivo sem separadores, `..`, controle e símbolos (nunca vazio)."""
    limpo = _PROIBIDOS.sub("", str(texto))
    limpo = _ESPACOS.sub(" ", limpo).strip(" .")
    while ".." in limpo:
        limpo = limpo.replace("..", ".")
    return limpo[:maximo].strip(" .") or padrao


def _celula(valor):
    """Valor de célula do CSV sem fórmula executável (apóstrofo antes dos gatilhos do Excel)."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def _decimal(valor):
    return str(valor).replace(".", ",") if valor not in (None, "") else ""


def filtrar_notas(filtros):
    """Notas (com XML) dos filtros: período de emissão, competência, situação e tomador."""
    situacoes = filtros.get("situacao") or [str(s) for s in SITUACOES_EXPORTAVEIS]
    if isinstance(situacoes, str):
        situacoes = [situacoes]
    situacoes = [s for s in situacoes if s in {str(x) for x in SITUACOES_EXPORTAVEIS}]
    consulta = Nfse.objects.filter(situacao__in=situacoes, xml_nfse__isnull=False)
    if filtros.get("periodo_inicio"):
        consulta = consulta.filter(emitida_em__date__gte=filtros["periodo_inicio"])
    if filtros.get("periodo_fim"):
        consulta = consulta.filter(emitida_em__date__lte=filtros["periodo_fim"])
    if filtros.get("competencia"):
        ano, mes = filtros["competencia"].split("-")
        consulta = consulta.filter(competencia__year=int(ano), competencia__month=int(mes))
    tomador = (filtros.get("tomador") or "").strip()
    if tomador:
        condicao = Q(tomador_nome__icontains=tomador)
        digitos = "".join(c for c in tomador if c.isdigit())
        if digitos:
            condicao |= Q(tomador_documento__startswith=digitos)
        consulta = consulta.filter(condicao)
    return consulta.order_by("emitida_em", "pk")


def solicitar(filtros, *, usuario, request=None):
    """Registra o pedido de lote (validando os limites) e devolve a `Exportacao` pendente."""
    total = filtrar_notas(filtros).count()
    if total == 0:
        raise ErroDeExportacao("Nenhuma nota encontrada com estes filtros.")
    if total > limite_de_notas():
        raise ErroDeExportacao(
            f"Estes filtros reúnem {total} notas e o limite de um lote é {limite_de_notas()}. "
            "Reduza o período ou separe em mais de um download."
        )
    exportacao = Exportacao.objects.create(
        solicitante_id=usuario.pk,
        solicitante_email=usuario.email,
        filtros=filtros,
        total=total,
    )
    auditoria.registrar(
        LogAuditoria.Acao.EXPORTACAO_SOLICITADA,
        request=request,
        usuario=usuario,
        empresa=contexto.empresa_atual(),
        alvo=f"exportacao:{exportacao.pk}",
        detalhes={"total": total},
    )
    return exportacao


def _nome_unico(base, extensao, usados):
    nome, n = f"{base}{extensao}", 2
    while nome.lower() in usados:
        nome = f"{base} ({n}){extensao}"
        n += 1
    usados.add(nome.lower())
    return nome


def gerar(exportacao_id, *, agora=None):
    """Gera o ZIP (XML + PDF + CSV). Idempotente: só roda se o pedido ainda está pendente."""
    agora = agora or contexto.agora()
    reservado = Exportacao.objects.filter(pk=exportacao_id, situacao=S.PENDENTE).update(
        situacao=S.GERANDO
    )
    exportacao = Exportacao.objects.get(pk=exportacao_id)
    if not reservado:
        return exportacao.situacao
    caminho = pasta_da_empresa() / f"{exportacao.pk}-{secrets.token_hex(8)}.zip"
    try:
        _montar_zip(exportacao, caminho)
    except ErroDeExportacao as erro:
        caminho.unlink(missing_ok=True)
        Exportacao.objects.filter(pk=exportacao.pk).update(
            situacao=S.FALHOU, erro=str(erro), concluido_em=agora
        )
    except Exception:
        logger.exception("Falha ao gerar a exportação %s", exportacao.pk)
        caminho.unlink(missing_ok=True)
        Exportacao.objects.filter(pk=exportacao.pk).update(
            situacao=S.FALHOU,
            erro="Não foi possível gerar o arquivo. Tente de novo; se persistir, avise o suporte.",
            concluido_em=agora,
        )
    else:
        Exportacao.objects.filter(pk=exportacao.pk).update(
            situacao=S.PRONTA,
            arquivo=caminho.name,
            nome_download=f"notas-{agora:%Y%m%d-%H%M}.zip",
            tamanho_bytes=caminho.stat().st_size,
            concluido_em=agora,
            expira_em=agora + retencao(),
        )
    return Exportacao.objects.get(pk=exportacao.pk).situacao


def _montar_zip(exportacao, caminho):
    empresa = contexto.empresa_atual()
    notas = list(filtrar_notas(exportacao.filtros))
    limite = limite_de_bytes()
    usados, avisos, linhas, bytes_total = set(), [], [], 0
    caminho.touch(mode=0o600)
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
        for indice, nfse in enumerate(notas, start=1):
            base = nome_seguro(
                f"NFSe {nfse.numero_nfse or nfse.pk} - {nfse.tomador_nome}", f"nota-{nfse.pk}"
            )
            xml = bytes(nfse.xml_nfse)
            nome_xml = f"xml/{_nome_unico(base, '.xml', usados)}"
            observacao, nome_pdf, pdf = "", "", None
            try:
                pdf = emissao.gerar_danfse(empresa, nfse)
                nome_pdf = f"pdf/{_nome_unico(base, '.pdf', usados)}"
            except emissao.ErroDeEmissao as erro:
                observacao = f"PDF indisponível: {erro}"
                avisos.append(f"Nota {nfse.numero_nfse or nfse.pk}: {observacao}")
            bytes_total += len(xml) + (len(pdf) if pdf else 0)
            if bytes_total > limite:
                raise ErroDeExportacao(
                    f"O lote passou de {limite // (1024 * 1024)} MB. Reduza o período ou separe "
                    "em mais de um download."
                )
            arquivo_zip.writestr(zipfile.ZipInfo(nome_xml, (2000, 1, 1, 0, 0, 0)), xml)
            if pdf is not None:
                arquivo_zip.writestr(zipfile.ZipInfo(nome_pdf, (2000, 1, 1, 0, 0, 0)), pdf)
            linhas.append(_linha_do_csv(nfse, nome_xml, nome_pdf, observacao))
            Exportacao.objects.filter(pk=exportacao.pk).update(processadas=indice)
        arquivo_zip.writestr(
            zipfile.ZipInfo("resumo.csv", (2000, 1, 1, 0, 0, 0)), _csv(linhas).encode("utf-8-sig")
        )
    Exportacao.objects.filter(pk=exportacao.pk).update(avisos=avisos)


def _linha_do_csv(nfse, nome_xml, nome_pdf, observacao):
    totais = nfse.totais or {}
    emissao_em = nfse.emitida_em.date().isoformat() if nfse.emitida_em else ""
    return {
        "numero_nfse": nfse.numero_nfse,
        "chave": nfse.chave,
        "serie_dps": nfse.serie,
        "numero_dps": nfse.numero_dps,
        "situacao": nfse.get_situacao_display(),
        "competencia": f"{nfse.competencia:%m/%Y}",
        "data_emissao": emissao_em,
        "tomador_nome": nfse.tomador_nome,
        "tomador_documento": nfse.tomador_documento,
        "valor_servico": _decimal(nfse.valor_servico),
        "base_calculo": _decimal(totais.get("base_calculo")),
        "valor_iss": _decimal(totais.get("valor_iss")),
        "total_retencoes": _decimal(totais.get("total_retencoes")),
        "valor_liquido": _decimal(totais.get("valor_liquido")),
        "ambiente": nfse.ambiente,
        "arquivo_xml": nome_xml,
        "arquivo_pdf": nome_pdf,
        "observacao": observacao,
    }


def _csv(linhas):
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(COLUNAS)
    for linha in linhas:
        escritor.writerow([_celula(linha[c]) for c in COLUNAS])
    return saida.getvalue()


# --- Download e expurgo --------------------------------------------------------------------


def abrir_para_download(exportacao, usuario, *, request=None, agora=None):
    """Caminho do ZIP, se `usuario` pediu e o arquivo existe (senão `ErroDeExportacao`)."""
    agora = agora or contexto.agora()
    if exportacao.solicitante_id != usuario.pk:
        raise ErroDeExportacao("Este download foi pedido por outra pessoa.")
    if exportacao.situacao != S.PRONTA or not exportacao.arquivo:
        raise ErroDeExportacao("Este download ainda não está pronto ou não está mais disponível.")
    if exportacao.expira_em and exportacao.expira_em <= agora:
        raise ErroDeExportacao("Este download expirou. Peça um novo.")
    caminho = pasta_da_empresa() / Path(exportacao.arquivo).name
    if not caminho.is_file():
        raise ErroDeExportacao("O arquivo não está mais disponível. Peça um novo download.")
    Exportacao.objects.filter(pk=exportacao.pk).update(baixado_em=agora)
    auditoria.registrar(
        LogAuditoria.Acao.EXPORTACAO_BAIXADA,
        request=request,
        usuario=usuario,
        empresa=contexto.empresa_atual(),
        alvo=f"exportacao:{exportacao.pk}",
    )
    return caminho


def expurgar(*, agora=None):
    """Apaga os ZIPs vencidos (e os sem registro) da empresa ativa. Devolve quantos apagou."""
    agora = agora or contexto.agora()
    apagados = 0
    for exportacao in Exportacao.objects.filter(situacao=S.PRONTA, expira_em__lte=agora):
        (pasta_da_empresa() / Path(exportacao.arquivo).name).unlink(missing_ok=True)
        Exportacao.objects.filter(pk=exportacao.pk).update(situacao=S.EXPIRADA, arquivo="")
        apagados += 1
    conhecidos = set(Exportacao.objects.exclude(arquivo="").values_list("arquivo", flat=True))
    limite = agora - retencao()
    for arquivo in pasta_da_empresa().glob("*.zip"):
        if (
            arquivo.name not in conhecidos
            and dt.datetime.fromtimestamp(arquivo.stat().st_mtime, dt.UTC) <= limite
        ):
            arquivo.unlink(missing_ok=True)
            apagados += 1
    return apagados
