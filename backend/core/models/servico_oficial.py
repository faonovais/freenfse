"""Cadastro oficial de serviços (LC 116 + NBS + IBS/CBS) compartilhado entre empresas."""

import re

from django.core.exceptions import ValidationError
from django.db import models


def _apenas_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


class ServicoOficial(models.Model):
    """Combinação oficial validada de LC 116, NBS, CST, cClassTrib e cIndOp."""

    codigo_tributacao_nacional = models.CharField("código de tributação nacional", max_length=6)
    descricao_item_lc116 = models.CharField(
        "descrição do item LC 116", max_length=500, blank=True
    )
    nbs = models.CharField("NBS", max_length=9)
    cst_ibs_cbs = models.CharField("CST do IBS/CBS", max_length=3)
    c_class_trib = models.CharField("classificação tributária (cClassTrib)", max_length=6)
    descricao_class_trib = models.CharField(
        "descrição da classificação tributária", max_length=500, blank=True
    )
    codigo_indicador_operacao = models.CharField("indicador da operação (cIndOp)", max_length=6)
    local_fornecimento = models.CharField("local de fornecimento", max_length=300, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "serviço oficial"
        verbose_name_plural = "serviços oficiais"
        ordering = [
            "codigo_tributacao_nacional",
            "nbs",
            "c_class_trib",
            "codigo_indicador_operacao",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "codigo_tributacao_nacional",
                    "nbs",
                    "cst_ibs_cbs",
                    "c_class_trib",
                    "codigo_indicador_operacao",
                ],
                name="servico_oficial_combinacao_unica",
            )
        ]

    def __str__(self):
        return (
            f"{self.codigo_tributacao_nacional} / NBS {self.nbs} / "
            f"cClassTrib {self.c_class_trib} / cIndOp {self.codigo_indicador_operacao}"
        )

    def clean(self):
        """Normaliza os códigos e valida a combinação contra as referências oficiais."""
        from fiscal.referencias import classificacao, incidencia, indop, local_fornecimento

        erros = {}
        self.codigo_tributacao_nacional = _apenas_digitos(self.codigo_tributacao_nacional)
        self.nbs = _apenas_digitos(self.nbs)
        self.cst_ibs_cbs = _apenas_digitos(self.cst_ibs_cbs)
        self.c_class_trib = _apenas_digitos(self.c_class_trib)
        self.codigo_indicador_operacao = _apenas_digitos(self.codigo_indicador_operacao)

        if len(self.codigo_tributacao_nacional) != 6:
            erros["codigo_tributacao_nacional"] = "O código de tributação nacional tem 6 dígitos."
        if len(self.nbs) != 9:
            erros["nbs"] = "A NBS tem 9 dígitos."
        if len(self.cst_ibs_cbs) != 3:
            erros["cst_ibs_cbs"] = "O CST do IBS/CBS tem 3 dígitos."
        if len(self.c_class_trib) != 6:
            erros["c_class_trib"] = "A classificação tributária (cClassTrib) tem 6 dígitos."
        elif self.cst_ibs_cbs and not self.c_class_trib.startswith(self.cst_ibs_cbs):
            erros["c_class_trib"] = (
                "Os 3 primeiros dígitos da classificação tributária devem ser iguais ao CST "
                "(regra E0959 da Sefin)."
            )
        if len(self.codigo_indicador_operacao) != 6:
            erros["codigo_indicador_operacao"] = "O indicador da operação (cIndOp) tem 6 dígitos."

        if (
            "codigo_tributacao_nacional" not in erros
            and "nbs" not in erros
            and "codigo_indicador_operacao" not in erros
        ):
            violacoes = indop.violacoes_do_indicador(
                self.codigo_tributacao_nacional, self.codigo_indicador_operacao
            )
            if violacoes:
                erros["codigo_indicador_operacao"] = violacoes[0][1]
            else:
                _item, correlacoes = indop.correlacao(self.codigo_tributacao_nacional, self.nbs)
                if not correlacoes:
                    erros["nbs"] = "O Anexo VIII não traz este código de tributação com esta NBS."
                elif self.codigo_indicador_operacao not in correlacoes:
                    erros["codigo_indicador_operacao"] = (
                        "Este indicador da operação não consta no Anexo VIII "
                        "para o código e a NBS informados."
                    )

        regra_class = None
        if "c_class_trib" not in erros:
            regra_class = classificacao.todas().get(self.c_class_trib)
            if regra_class is None:
                erros["c_class_trib"] = "A classificação tributária não consta da tabela oficial."
            elif not regra_class.aceita_nfse:
                erros["c_class_trib"] = "Esta classificação tributária não é aceita na NFS-e."

        if erros:
            raise ValidationError(erros)

        regras_incidencia = {
            _apenas_digitos(codigo): desc for codigo, desc in incidencia.todas_as_regras().items()
        }
        descricao_lc116 = (
            self.descricao_item_lc116 or ""
        ).strip() or regras_incidencia.get(self.codigo_tributacao_nacional, "")
        self.descricao_item_lc116 = descricao_lc116[:500]
        if regra_class is not None:
            self.descricao_class_trib = (regra_class.descricao or "")[:500]
        local_desc = local_fornecimento.descricao(self.codigo_indicador_operacao) or ""
        self.local_fornecimento = local_desc[:300]
