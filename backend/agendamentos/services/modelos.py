"""Modelos de NFS-e: validação, geração do rascunho (snapshot) e sobreposição de e-mail.

Gerar uma nota a partir do modelo **copia** os dados para a nota (`fiscal.services.nfse`):
alterar o modelo depois nunca muda uma nota já criada, nem a configuração de e-mail dela.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from agendamentos.models import ModeloNfse, OrigemNfse
from cadastros.models import Servico
from documentos.services import envio_email, modelos_texto
from fiscal.services import nfse as servico_nfse
from fiscal.services.nfse import ErroDeNota

TAMANHO_MAXIMO_DO_TEXTO = 2000

VARIAVEIS_DO_TEXTO = {
    "competencia": "Competência da nota (MM/AAAA)",
    "mes": "Mês da competência (01 a 12)",
    "ano": "Ano da competência (AAAA)",
    "data_execucao": "Data da execução (DD/MM/AAAA)",
}


def competencia_do_rascunho(modelo, data_execucao):
    """Primeiro dia da competência: o mês da execução ou o anterior, conforme o modelo."""
    primeiro_dia = data_execucao.replace(day=1)
    if modelo.competencia_padrao == ModeloNfse.Competencia.MES_ANTERIOR:
        return (primeiro_dia - dt.timedelta(days=1)).replace(day=1)
    return primeiro_dia


def _valores_do_texto(competencia, data_execucao):
    return {
        "competencia": f"{competencia:%m/%Y}",
        "mes": f"{competencia:%m}",
        "ano": f"{competencia:%Y}",
        "data_execucao": f"{data_execucao:%d/%m/%Y}",
    }


def problemas_do_texto(texto):
    """Frases sobre variável desconhecida ou chave solta no texto complementar."""
    problemas, _usadas = modelos_texto.analisar(texto, set(VARIAVEIS_DO_TEXTO))
    return problemas


def dados_do_rascunho(modelo, *, data_execucao):
    """Monta a entrada de `criar_rascunho` com os dados do modelo para aquela execução.

    O serviço é a versão **vigente na competência** com os mesmos códigos de tributação do
    serviço do modelo. Levanta `ErroDeNota` (um erro por campo, em linguagem simples).
    """
    erros = {}
    if not modelo.ativo:
        erros["modelo"] = f"O modelo “{modelo.nome}” está inativo."
    if modelo.tomador_id is None:
        erros["tomador"] = "O tomador deste modelo não existe mais. Escolha outro no modelo."
    competencia = competencia_do_rascunho(modelo, data_execucao)
    servico = None
    if modelo.servico_id is None:
        erros["servico"] = "O serviço deste modelo não existe mais. Escolha outro no modelo."
    else:
        base = modelo.servico
        servico = Servico.objects.vigente(
            competencia, base.codigo_tributacao_nacional, base.codigo_tributacao_municipal
        )
        if servico is None:
            erros["servico"] = (
                f"O serviço “{base.nome}” não tem versão vigente em {competencia:%m/%Y}. "
                "Cadastre a vigência em Cadastros › Serviços."
            )
    if erros:
        raise ErroDeNota(erros)
    complementos = modelo.complementos or {}
    texto = modelos_texto.renderizar(
        complementos.get("informacoes_complementares", ""),
        _valores_do_texto(competencia, data_execucao),
    ).strip()
    return {
        "tomador": modelo.tomador_id,
        "servico": servico.pk,
        "competencia": competencia,
        "valores": dict(modelo.valores or {}),
        "informacoes_complementares": texto,
        "percentual_total_tributos_simples": complementos.get("percentual_total_tributos_simples"),
        # IBS/CBS não é do modelo: a opção e o indicador são da empresa (ADR 0006).
    }


def validar_modelo(modelo, *, hoje, com_geracao=True):
    """Erros do modelo por campo (vazio = válido), sem gravar nada.

    Modelo inativo só precisa de nome: pode ficar incompleto até ser ativado. Ativo, precisa
    gerar um rascunho válido hoje (tomador ativo, serviço vigente, valores coerentes);
    `com_geracao=False` pula essa prova (alterar só o e-mail não depende do serviço).
    """
    erros = {}
    if not (modelo.nome or "").strip():
        erros["nome"] = "Dê um nome ao modelo."
    texto = (modelo.complementos or {}).get("informacoes_complementares", "")
    if len(texto) > TAMANHO_MAXIMO_DO_TEXTO:
        erros["informacoes_complementares"] = (
            f"O texto passa de {TAMANHO_MAXIMO_DO_TEXTO} caracteres."
        )
    elif problemas := problemas_do_texto(texto):
        erros["informacoes_complementares"] = " ".join(problemas)
    for campo, mensagem in envio_email.validar_modelos(
        modelo.email_assunto_modelo, modelo.email_corpo_modelo
    ).items():
        erros[f"email_{campo}"] = mensagem
    for email in modelo.email_copias_fixas or []:
        try:
            validate_email(str(email))
        except ValidationError:
            erros["email_copias_fixas"] = f"E-mail inválido: {email}."
            break
    if modelo.ativo and com_geracao and not erros:
        erros.update(erros_de_preparo(modelo, hoje=hoje))
    return erros


def erros_de_preparo(modelo, *, hoje):
    """Roda a validação da nota (sem gravar) e devolve os erros por campo."""
    try:
        servico_nfse.preparar(dados_do_rascunho(modelo, data_execucao=hoje), hoje=hoje)
    except ErroDeNota as erro:
        return dict(erro.erros)
    return {}


def gerar_rascunho(modelo, *, usuario, data_execucao, execucao=None):
    """Cria o rascunho (com a cópia dos dados) e registra de onde ele veio.

    Tudo ou nada: se algo falhar, nem o rascunho nem a origem ficam. Levanta `ErroDeNota`.
    """
    dados = dados_do_rascunho(modelo, data_execucao=data_execucao)
    with transaction.atomic():
        nfse = servico_nfse.criar_rascunho(dados, usuario=usuario, hoje=data_execucao)
        OrigemNfse.objects.create(
            nfse=nfse,
            modelo=modelo,
            modelo_nome=modelo.nome,
            execucao=execucao,
            email=modelo.sobreposicao_de_email(),  # cópia: mudar o modelo depois não altera a nota
        )
    nfse.refresh_from_db()  # valores com os tipos do banco (decimal, data)
    return nfse


def sobreposicao_de_email(nfse):
    """Ponto de extensão da Fase 4: o que o modelo de origem muda no e-mail desta nota."""
    copia = OrigemNfse.objects.filter(nfse_id=nfse.pk).values_list("email", flat=True).first()
    return dict(copia or {})
