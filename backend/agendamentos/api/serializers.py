"""Entrada e saída da API de agendamentos: modelos de NFS-e, agendamentos, execuções, rascunhos."""

from rest_framework import serializers

from agendamentos.models import Agendamento, ExecucaoAgendamento, ModeloNfse
from agendamentos.services import modelos
from cadastros.models import Pessoa, Servico
from fiscal.services.nfse import CAMPOS_DE_VALORES

CAMPOS_DE_EMAIL = (
    "email_envio_automatico",
    "email_avisar_cancelamento",
    "email_anexar_pdf",
    "email_anexar_xml",
    "email_assunto_modelo",
    "email_corpo_modelo",
    "email_copias_fixas",
)


class ModeloEntrada(serializers.Serializer):
    """Corpo de criação/alteração do modelo. Campos ausentes ficam como estão (PATCH)."""

    nome = serializers.CharField(max_length=120, required=False, allow_blank=True)
    ativo = serializers.BooleanField(required=False)
    tomador = serializers.IntegerField(required=False, allow_null=True)
    servico = serializers.IntegerField(required=False, allow_null=True)
    valores = serializers.DictField(required=False)
    informacoes_complementares = serializers.CharField(required=False, allow_blank=True)
    percentual_total_tributos_simples = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    ibs_cbs = serializers.DictField(required=False, allow_null=True)
    competencia_padrao = serializers.ChoiceField(
        choices=ModeloNfse.Competencia.choices, required=False
    )
    email_envio_automatico = serializers.BooleanField(required=False, allow_null=True)
    email_avisar_cancelamento = serializers.BooleanField(required=False, allow_null=True)
    email_anexar_pdf = serializers.BooleanField(required=False, allow_null=True)
    email_anexar_xml = serializers.BooleanField(required=False, allow_null=True)
    email_assunto_modelo = serializers.CharField(max_length=200, required=False, allow_blank=True)
    email_corpo_modelo = serializers.CharField(required=False, allow_blank=True)
    email_copias_fixas = serializers.ListField(
        child=serializers.CharField(), required=False, allow_null=True
    )


def aplicar_modelo(modelo, dados):
    """Copia `dados` (validados) para o modelo e devolve `{campo: erro}` de referências."""
    erros = {}
    for campo in ("nome", "ativo", "competencia_padrao", *CAMPOS_DE_EMAIL):
        if campo in dados:
            valor = dados[campo]
            setattr(modelo, campo, valor.strip() if campo == "nome" else valor)
    for campo, classe, rotulo in (
        ("tomador", Pessoa, "Tomador"),
        ("servico", Servico, "Serviço"),
    ):
        if campo in dados:
            objeto = classe.objects.filter(pk=dados[campo]).first() if dados[campo] else None
            if dados[campo] and objeto is None:
                erros[campo] = f"{rotulo} não encontrado."
            setattr(modelo, campo, objeto)
    if "valores" in dados:
        modelo.valores = {
            campo: (
                None if dados["valores"].get(campo) in (None, "") else str(dados["valores"][campo])
            )
            for campo in CAMPOS_DE_VALORES
            if campo in dados["valores"]
        }
    complementos = dict(modelo.complementos or {})
    for campo in ("informacoes_complementares", "percentual_total_tributos_simples", "ibs_cbs"):
        if campo in dados:
            complementos[campo] = dados[campo]
    modelo.complementos = complementos
    return erros


def modelo_saida(modelo, *, problemas=None, em_uso=0):
    """Dados do modelo para a tela, com os problemas que o impedem de gerar rascunho hoje."""
    complementos = modelo.complementos or {}
    return {
        "id": modelo.pk,
        "nome": modelo.nome,
        "ativo": modelo.ativo,
        "tomador": modelo.tomador_id,
        "tomador_nome": modelo.tomador.nome if modelo.tomador_id else "",
        "servico": modelo.servico_id,
        "servico_nome": modelo.servico.nome if modelo.servico_id else "",
        "valores": modelo.valores or {},
        "informacoes_complementares": complementos.get("informacoes_complementares", ""),
        "percentual_total_tributos_simples": complementos.get("percentual_total_tributos_simples"),
        "ibs_cbs": complementos.get("ibs_cbs"),
        "competencia_padrao": modelo.competencia_padrao,
        "email_envio_automatico": modelo.email_envio_automatico,
        "email_avisar_cancelamento": modelo.email_avisar_cancelamento,
        "email_anexar_pdf": modelo.email_anexar_pdf,
        "email_anexar_xml": modelo.email_anexar_xml,
        "email_assunto_modelo": modelo.email_assunto_modelo,
        "email_corpo_modelo": modelo.email_corpo_modelo,
        "email_copias_fixas": modelo.email_copias_fixas,
        "agendamentos_em_uso": em_uso,
        "problemas": problemas or {},
        "atualizado_em": modelo.atualizado_em,
    }


class AgendamentoEntrada(serializers.Serializer):
    """Corpo de criação/alteração do agendamento. Campos ausentes ficam como estão (PATCH)."""

    nome = serializers.CharField(max_length=120, required=False, allow_blank=True)
    modelo = serializers.IntegerField(required=False)
    responsavel = serializers.IntegerField(required=False)
    frequencia = serializers.ChoiceField(choices=Agendamento.Frequencia.choices, required=False)
    intervalo = serializers.IntegerField(required=False)
    dias_semana = serializers.ListField(child=serializers.IntegerField(), required=False)
    dia_do_mes = serializers.IntegerField(required=False, allow_null=True)
    mes = serializers.IntegerField(required=False, allow_null=True)
    hora = serializers.TimeField(required=False, input_formats=["%H:%M", "%H:%M:%S"])
    data_inicio = serializers.DateField(required=False)
    data_fim = serializers.DateField(required=False, allow_null=True)
    max_execucoes = serializers.IntegerField(required=False, allow_null=True)


class PreviaDeDatasEntrada(AgendamentoEntrada):
    """Regra a pré-visualizar (não grava nada). `agendamento` aproveita as execuções já feitas."""

    agendamento = serializers.IntegerField(required=False)
    quantidade = serializers.IntegerField(required=False, min_value=1, max_value=24, default=6)


def instante_saida(instante):
    """Um instante da série para a tela: UTC e a data/hora de Brasília."""
    from agendamentos import recorrencia

    local = instante.astimezone(recorrencia.FUSO)
    return {
        "instante": instante,
        "data": local.date().isoformat(),
        "hora": local.strftime("%H:%M"),
        "dia_da_semana": local.weekday(),
    }


def agendamento_saida(agendamento, *, proximas=None):
    """Dados do agendamento para a tela."""
    return {
        "id": agendamento.pk,
        "nome": agendamento.nome,
        "modelo": agendamento.modelo_id,
        "modelo_nome": agendamento.modelo.nome,
        "responsavel": agendamento.responsavel_id,
        "responsavel_email": agendamento.responsavel_email,
        "frequencia": agendamento.frequencia,
        "frequencia_rotulo": agendamento.get_frequencia_display(),
        "intervalo": agendamento.intervalo,
        "dias_semana": agendamento.dias_semana or [],
        "dia_do_mes": agendamento.dia_do_mes,
        "mes": agendamento.mes,
        "hora": agendamento.hora.strftime("%H:%M"),
        "data_inicio": agendamento.data_inicio,
        "data_fim": agendamento.data_fim,
        "max_execucoes": agendamento.max_execucoes,
        "situacao": agendamento.situacao,
        "situacao_rotulo": agendamento.get_situacao_display(),
        "motivo_situacao": agendamento.motivo_situacao,
        "execucoes_realizadas": agendamento.execucoes_realizadas,
        "proxima_execucao": agendamento.proxima_execucao,
        "proximas": [instante_saida(i) for i in proximas or []],
    }


class ExecucaoSerializer(serializers.ModelSerializer):
    """Linha do histórico de execuções."""

    agendamento_nome = serializers.CharField(source="agendamento.nome", read_only=True)
    situacao_rotulo = serializers.CharField(source="get_situacao_display", read_only=True)
    nfse_situacao = serializers.CharField(source="nfse.situacao", read_only=True, default=None)

    class Meta:
        model = ExecucaoAgendamento
        fields = [
            "id", "agendamento", "agendamento_nome", "data_execucao", "previsto_para", "situacao",
            "situacao_rotulo", "erro", "nfse", "nfse_situacao", "concluido_em",
        ]  # fmt: skip


def variaveis_do_texto():
    """Variáveis aceitas no texto complementar do modelo."""
    return modelos.VARIAVEIS_DO_TEXTO
