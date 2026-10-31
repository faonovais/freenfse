"""Cópia das notas ao Google Drive: pastas sem duplicar, nomes únicos e sobrescrita por `fileId`.

Regras que importam (o Drive aceita **vários itens com o mesmo nome**, então o sistema as impõe):

- **Pastas:** o mapa `caminho → ID` é guardado no banco (`PastaDrive`, com unicidade) e a criação
  roda sob uma trava por empresa. O Drive não é consultado por nome *antes* do cache, porque a
  listagem dele pode atrasar: duas cópias simultâneas criariam a mesma pasta duas vezes.
- **Nomes:** se já existe, na pasta, um arquivo com o nome de **outra** nota, este recebe o sufixo
  " (2)", " (3)"… e a nota fica com um aviso. Arquivo que o sistema já gravou antes (marcado com
  `appProperties`) é reaproveitado, não duplicado.
- **Sobrescrita:** o `fileId` de cada arquivo fica gravado; reenviar e trocar o PDF (marca d'água)
  atualiza o mesmo arquivo.
- **Falhas:** temporárias reagendam com espera crescente (persistida); permanentes encerram com
  explicação simples.
"""

import hashlib
import logging

from django.utils import timezone

from core.models import LogAuditoria
from core.services import auditoria
from core.travas import TravaDeSessao, TravaOcupada
from documentos.models import ArquivoDrive, ConfiguracaoDrive, PastaDrive
from documentos.services import contexto
from documentos.services.credenciais import CredencialInvalida, ler_conta_de_servico
from documentos.services.drive import caminhos
from documentos.services.drive.cliente import ClienteDriveGoogle, ErroDrive, criar_servico_drive
from fiscal.models import Nfse
from fiscal.services import emissao

logger = logging.getLogger(__name__)

S = ArquivoDrive.Situacao
ESPERA_DA_TRAVA = 60.0
ROTULOS_DE_EVENTO = {
    "101101": "cancelamento",
    "105102": "substituicao",
    "105104": "cancelamento_analise_fiscal",
    "305101": "cancelamento_oficio",
}
SITUACOES_COM_COPIA = (
    Nfse.Situacao.AUTORIZADA,
    Nfse.Situacao.CANCELADA,
    Nfse.Situacao.SUBSTITUIDA,
)


class ErroDeConfiguracaoDrive(Exception):
    """A configuração do Drive não pôde ser salva; `erros` mapeia o campo às mensagens."""

    def __init__(self, erros):
        """Guarda os erros por campo (listas de frases)."""
        super().__init__("; ".join(m for v in erros.values() for m in v))
        self.erros = erros


def pontos_de_troca():
    """Fábrica do cliente do Drive. Os testes trocam por um Drive simulado, sem rede."""
    return {"cliente": None}


def criar_cliente(configuracao, trocas=None):
    """Cliente do Drive da empresa, ou `ErroDrive` didático se a credencial não serve."""
    trocas = {**pontos_de_troca(), **(trocas or {})}
    if trocas["cliente"]:
        return trocas["cliente"](configuracao)
    try:
        conta = ler_conta_de_servico(configuracao.conta_servico)
        return ClienteDriveGoogle(criar_servico_drive(conta))
    except CredencialInvalida as erro:
        raise ErroDrive(str(erro), temporario=False) from None


# --- Configuração --------------------------------------------------------------------------


def salvar_configuracao(*, dados, usuario, request=None, trocas=None, agora=None):
    """Valida (modelos, credencial e acesso de escrita à pasta raiz) e grava a configuração.

    Levanta `ErroDeConfiguracaoDrive` com **todos** os erros encontrados. A credencial nunca é
    devolvida: só o e-mail da conta de serviço (que o usuário precisa para compartilhar a pasta).
    """
    agora = agora or contexto.agora()
    configuracao = ConfiguracaoDrive.obter()
    erros = {}

    if dados.get("conta_servico"):
        try:
            conta = ler_conta_de_servico(dados["conta_servico"])
            configuracao.conta_servico = dados["conta_servico"]
            configuracao.conta_servico_email = conta["client_email"]
        except CredencialInvalida as erro:
            erros["conta_servico"] = [str(erro)]

    subpastas = dados.get("modelo_subpastas", configuracao.modelo_subpastas)
    arquivo = dados.get("modelo_arquivo", configuracao.modelo_arquivo)
    for campo, mensagens in caminhos.validar(subpastas, arquivo).items():
        erros[campo] = mensagens
    ativo = bool(dados.get("ativo", configuracao.ativo))
    raiz = str(dados.get("pasta_raiz_id", configuracao.pasta_raiz_id) or "").strip()

    if ativo and not raiz:
        erros["pasta_raiz_id"] = [
            "Informe o ID da pasta raiz do Google Drive (o final da URL da pasta)."
        ]
    if ativo and not configuracao.conta_servico and "conta_servico" not in erros:
        erros["conta_servico"] = ["Envie a chave JSON da conta de serviço do Google."]
    nome_da_pasta = configuracao.pasta_raiz_nome
    if (
        raiz
        and configuracao.conta_servico
        and "conta_servico" not in erros
        and "pasta_raiz_id" not in erros
    ):
        try:
            pasta = criar_cliente(configuracao, trocas).obter_pasta(raiz)
            if not pasta["pode_escrever"]:
                erros["pasta_raiz_id"] = [
                    "A conta de serviço enxerga a pasta mas não pode gravar nela. Compartilhe a "
                    f"pasta com {configuracao.conta_servico_email} como Editor."
                ]
            else:
                nome_da_pasta = pasta["nome"]
        except ErroDrive as erro:
            erros["pasta_raiz_id"] = [erro.mensagem]
    if erros:
        raise ErroDeConfiguracaoDrive(erros)

    configuracao.modelo_subpastas = (subpastas or "").strip()
    configuracao.modelo_arquivo = (arquivo or "").strip()
    configuracao.pasta_raiz_id = raiz
    configuracao.pasta_raiz_nome = nome_da_pasta if raiz else ""
    configuracao.ativo = ativo
    if "enviar_automaticamente" in dados:
        configuracao.enviar_automaticamente = bool(dados["enviar_automaticamente"])
    if raiz and configuracao.conta_servico:
        configuracao.validado_em = agora
    configuracao.save()
    auditoria.registrar(
        LogAuditoria.Acao.DRIVE_CONFIG_ALTERADA,
        request=request,
        usuario=usuario,
        empresa=contexto.empresa_atual(),
        alvo="drive",
        detalhes={"ativo": configuracao.ativo, "pasta_raiz_id": raiz},
    )
    return configuracao


# --- Pastas, nomes e arquivos --------------------------------------------------------------


def resolver_pasta(cliente, configuracao, niveis):
    """Devolva o ID da pasta do caminho, criando o que faltar (chamar sob a trava da empresa)."""
    raiz = configuracao.pasta_raiz_id
    pai, caminho = raiz, ""
    for nivel in niveis:
        caminho = f"{caminho}/{nivel}" if caminho else nivel
        registro = PastaDrive.objects.filter(pasta_raiz_id=raiz, caminho=caminho).first()
        if registro:
            pai = registro.pasta_id
            continue
        existentes = cliente.listar(pai, nome=nivel, somente_pastas=True)
        pasta_id = existentes[0]["id"] if existentes else cliente.criar_pasta(nivel, pai)
        PastaDrive.objects.create(pasta_raiz_id=raiz, caminho=caminho, pasta_id=pasta_id)
        pai = pasta_id
    return pai


def _esquecer_pastas(configuracao, niveis):
    """Apague do cache o caminho e tudo abaixo dele (a pasta sumiu do Drive)."""
    PastaDrive.objects.filter(pasta_raiz_id=configuracao.pasta_raiz_id).filter(
        caminho__in=["/".join(niveis[: i + 1]) for i in range(len(niveis))]
    ).delete()


def _marca_do_arquivo(arquivo, nfse):
    """Propriedades gravadas no arquivo para reconhecê-lo depois (curtas: limite de 124 bytes)."""
    return {
        "freenfse_nota": nfse.chave or str(nfse.pk),
        "freenfse_papel": hashlib.sha1(arquivo.papel.encode()).hexdigest()[:12],  # noqa: S324
    }


def _nome_livre(cliente, pasta_id, nome, arquivo, nfse):
    """`(nome, aviso, file_id_proprio)`: o nome a usar na pasta, sem colidir com outra nota."""
    marca = _marca_do_arquivo(arquivo, nfse)
    stem, _, extensao = nome.rpartition(".")
    n = 1
    while True:
        candidato = nome if n == 1 else f"{stem} ({n}).{extensao}"
        existentes = cliente.listar(pasta_id, nome=candidato)
        proprios = [
            e for e in existentes if all(e["propriedades"].get(k) == v for k, v in marca.items())
        ]
        if proprios:
            return candidato, "", proprios[0]["id"]
        ocupado = ArquivoDrive.objects.filter(pasta_id=pasta_id, nome=candidato).exclude(
            pk=arquivo.pk
        )
        if not existentes and not ocupado.exists():
            aviso = (
                f"Já existia na pasta um arquivo com o nome {nome!r} de outra nota; este foi "
                f"gravado como {candidato!r}."
                if n > 1
                else ""
            )
            return candidato, aviso, ""
        n += 1


def _reservar(arquivo, agora):
    reservado = (
        ArquivoDrive.objects.filter(pk=arquivo.pk, situacao=S.PENDENTE)
        .filter(proxima_tentativa__lte=agora)
        .update(proxima_tentativa=agora + contexto.RESERVA_DA_TENTATIVA)
    )
    return bool(reservado)


def _linha(nfse, papel, agora):
    arquivo, _ = ArquivoDrive.objects.get_or_create(nfse=nfse, papel=papel)
    return arquivo


def _marcar_pendente(arquivo, agora):
    ArquivoDrive.objects.filter(pk=arquivo.pk).update(
        situacao=S.PENDENTE, proxima_tentativa=agora, erro=""
    )
    arquivo.refresh_from_db()


def _tipo_e_extensao(papel):
    return ("application/pdf", ".pdf") if papel == "pdf" else ("application/xml", ".xml")


def _nome_do_evento(nfse, base, evento):
    rotulo = ROTULOS_DE_EVENTO.get(evento.tipo_evento, f"evento_{evento.tipo_evento}")
    return f"{base}_{rotulo}"


def _enviar_arquivo(arquivo, *, nfse, empresa, configuracao, cliente, conteudo, agora, evento=None):
    """Grava (ou sobrescreve) um arquivo. Devolve a situação final."""
    if not _reservar(arquivo, agora):
        return arquivo.situacao
    arquivo.refresh_from_db()
    mime, extensao = _tipo_e_extensao(arquivo.papel)
    try:
        corpo = conteudo()
        if arquivo.file_id:
            try:
                cliente.atualizar(arquivo.file_id, corpo, mime)
            except ErroDrive as erro:
                if not erro.nao_encontrado:
                    raise
                arquivo.file_id = ""  # o usuário apagou o arquivo no Drive: recria
        if not arquivo.file_id:
            _criar(arquivo, nfse, empresa, configuracao, cliente, corpo, mime, extensao, evento)
        arquivo.situacao = S.ENVIADO
        arquivo.enviado_em = timezone.now() if agora is None else agora
        arquivo.proxima_tentativa = None
        arquivo.erro = ""
    except emissao.ErroDeEmissao as erro:
        _falhar(arquivo, ErroDrive(str(erro), detalhe="PDF indisponível"), agora)
    except TravaOcupada:
        _falhar(
            arquivo, ErroDrive("Outra cópia ao Drive está em andamento.", detalhe="trava"), agora
        )
    except ErroDrive as erro:
        _falhar(arquivo, erro, agora)
    else:
        arquivo.tentativas += 1
        arquivo.save()
    return arquivo.situacao


def _falhar(arquivo, erro, agora):
    arquivo.tentativas += 1
    arquivo.erro = erro.mensagem
    if erro.temporario and arquivo.tentativas < 5:
        arquivo.situacao = S.PENDENTE
        arquivo.proxima_tentativa = agora + contexto.espera_apos(arquivo.tentativas)
    else:
        arquivo.situacao = S.FALHOU
        arquivo.proxima_tentativa = None
    arquivo.save()


def _criar(arquivo, nfse, empresa, configuracao, cliente, corpo, mime, extensao, evento):
    niveis, base = caminhos.caminho_da_nota(configuracao, nfse, empresa)
    nome_base = _nome_do_evento(nfse, base, evento) if evento else base
    with TravaDeSessao("drive", espera_segundos=ESPERA_DA_TRAVA):
        for tentativa in (1, 2):
            try:
                pasta_id = resolver_pasta(cliente, configuracao, niveis)
                nome, aviso, proprio = _nome_livre(
                    cliente, pasta_id, f"{nome_base}{extensao}", arquivo, nfse
                )
                if proprio:
                    cliente.atualizar(proprio, corpo, mime)
                    arquivo.file_id = proprio
                else:
                    arquivo.file_id = cliente.enviar(
                        nome, pasta_id, corpo, mime, _marca_do_arquivo(arquivo, nfse)
                    )
                break
            except ErroDrive as erro:
                if tentativa == 1 and erro.nao_encontrado and niveis:
                    _esquecer_pastas(configuracao, niveis)  # a pasta do cache não existe mais
                    continue
                raise
        arquivo.pasta_id, arquivo.nome, arquivo.aviso = pasta_id, nome, aviso
        arquivo.caminho = "/".join(niveis)
        arquivo.save()  # ainda sob a trava: o próximo a entrar já enxerga este nome


# --- Operações por nota --------------------------------------------------------------------


def _contexto_da_cópia(trocas):
    configuracao = ConfiguracaoDrive.obter()
    if not configuracao.ativo:
        return None
    return configuracao, criar_cliente(configuracao, trocas), contexto.empresa_atual()


def enviar_nota(nfse, *, trocas=None, agora=None, forcar=False, papeis=None):
    """Copia o XML e o PDF da nota (e os XMLs dos eventos já conhecidos) ao Drive.

    `papeis` (opcional) restringe a cópia, por exemplo a `("xml",)`.
    """
    agora = agora or contexto.agora()
    preparado = _contexto_da_cópia(trocas)
    if preparado is None:
        return {}
    configuracao, cliente, empresa = preparado
    resultado = {}
    linhas = [
        ("xml", lambda: bytes(nfse.xml_nfse), None),
        ("pdf", lambda: emissao.gerar_danfse(empresa, nfse), None),
    ]
    for evento in nfse.eventos.exclude(xml__isnull=True):
        linhas.append((_papel_do_evento(evento), lambda e=evento: bytes(e.xml), evento))
    for papel, conteudo, evento in linhas:
        if papeis is not None and papel not in papeis:
            continue
        arquivo = _linha(nfse, papel, agora)
        if forcar or arquivo.situacao == S.FALHOU:
            _marcar_pendente(arquivo, agora)
        elif arquivo.situacao == S.PENDENTE and arquivo.proxima_tentativa is None:
            _marcar_pendente(arquivo, agora)
        resultado[papel] = _enviar_arquivo(
            arquivo, nfse=nfse, empresa=empresa, configuracao=configuracao, cliente=cliente,
            conteudo=conteudo, agora=agora, evento=evento,
        )  # fmt: skip
    return resultado


def _papel_do_evento(evento):
    return f"evento:{evento.tipo_evento}:{evento.pk}"


def enviar_evento(nfse, evento, *, trocas=None, agora=None):
    """Grava o XML do evento (com sufixo) e **substitui** o PDF pelo da nota com marca d'água."""
    agora = agora or contexto.agora()
    preparado = _contexto_da_cópia(trocas)
    if preparado is None:
        return {}
    configuracao, cliente, empresa = preparado
    resultado = {}
    arquivo_evento = _linha(nfse, _papel_do_evento(evento), agora)
    _marcar_pendente(arquivo_evento, agora)
    resultado["evento"] = _enviar_arquivo(
        arquivo_evento, nfse=nfse, empresa=empresa, configuracao=configuracao, cliente=cliente,
        conteudo=lambda: bytes(evento.xml), agora=agora, evento=evento,
    )  # fmt: skip
    pdf = _linha(nfse, "pdf", agora)
    _marcar_pendente(pdf, agora)  # o PDF já enviado (mesmo fileId) é sobrescrito
    resultado["pdf"] = _enviar_arquivo(
        pdf, nfse=nfse, empresa=empresa, configuracao=configuracao, cliente=cliente,
        conteudo=lambda: emissao.gerar_danfse(empresa, nfse), agora=agora,
    )  # fmt: skip
    return resultado


def reenviar(nfse, *, usuario, request=None, trocas=None, agora=None):
    """Refaça a cópia da nota ao Drive com o modelo vigente (mesmo `fileId`, sem duplicar)."""
    resultado = enviar_nota(nfse, trocas=trocas, agora=agora, forcar=True)
    auditoria.registrar(
        LogAuditoria.Acao.DRIVE_REENVIADO,
        request=request,
        usuario=usuario,
        empresa=contexto.empresa_atual(),
        alvo=f"nfse:{nfse.pk}",
    )
    return resultado


def notas_do_periodo(inicio=None, fim=None):
    """Notas com cópia no Drive cuja **data de emissão** cai no período (inclusive)."""
    consulta = Nfse.objects.filter(situacao__in=SITUACOES_COM_COPIA, xml_nfse__isnull=False)
    if inicio:
        consulta = consulta.filter(emitida_em__date__gte=inicio)
    if fim:
        consulta = consulta.filter(emitida_em__date__lte=fim)
    return consulta.order_by("emitida_em", "pk")


def pendentes_vencidos(agora=None):
    """Ids das notas com arquivo pendente cuja hora de tentar já chegou."""
    agora = agora or contexto.agora()
    return sorted(
        set(
            ArquivoDrive.objects.filter(
                situacao=S.PENDENTE, proxima_tentativa__lte=agora
            ).values_list("nfse_id", flat=True)
        )
    )
