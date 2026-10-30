"""Cadastros da empresa (no schema de cada empresa): perfis, pessoas e serviços."""

import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, validate_email
from django.db import models
from django.db.models import Q

from core.services import municipios
from core.validators import cnpj_valido, cpf_valido, normalizar_cnpj, normalizar_cpf

MAXIMO_EMAILS_DE_ENVIO = 10


def _apenas_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


class PerfilPessoa(models.Model):
    """Papel que uma pessoa tem para a empresa (cliente, fornecedor, intermediário…).

    Os perfis padrão (`sistema=True`) vêm da migração; a empresa pode cadastrar outros.
    """

    codigo = models.SlugField(max_length=30, unique=True)
    nome = models.CharField(max_length=60)
    sistema = models.BooleanField(default=False, editable=False)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "perfil de pessoa"
        verbose_name_plural = "perfis de pessoa"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Pessoa(models.Model):
    """Pessoa física, jurídica ou estrangeira (tomador, fornecedor, intermediário…).

    Cadastro **por empresa**, isolado (D4). Os campos seguem a identificação e o endereço da
    DPS: exatamente um entre CPF/CNPJ, NIF ou motivo de ausência do NIF, e endereço nacional
    (com município IBGE) ou no exterior.
    """

    class Tipo(models.TextChoices):
        """Natureza da pessoa."""

        PESSOA_FISICA = "pf", "Pessoa física"
        PESSOA_JURIDICA = "pj", "Pessoa jurídica"
        ESTRANGEIRO = "estrangeiro", "Estrangeiro"

    class MotivoSemNif(models.IntegerChoices):
        """`cNaoNIF` da DPS: por que o NIF do estrangeiro não foi informado."""

        NAO_INFORMADO = 0, "Não informado na nota de origem"
        DISPENSADO = 1, "Dispensado do NIF"
        NAO_EXIGIDO = 2, "Não exigência do NIF"

    tipo = models.CharField(max_length=12, choices=Tipo)
    documento = models.CharField(
        "CPF/CNPJ", max_length=14, blank=True, help_text="Só dígitos (CNPJ pode ter letras)."
    )
    nif = models.CharField("NIF", max_length=40, blank=True)
    motivo_sem_nif = models.PositiveSmallIntegerField(
        "motivo sem NIF", choices=MotivoSemNif, null=True, blank=True
    )
    nome = models.CharField("nome ou razão social", max_length=300)
    inscricao_municipal = models.CharField("inscrição municipal", max_length=15, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    emails_envio = models.JSONField("e-mails de envio da nota", default=list, blank=True)

    # Endereço nacional
    logradouro = models.CharField(max_length=255, blank=True)
    numero = models.CharField("número", max_length=60, blank=True)
    complemento = models.CharField(max_length=156, blank=True)
    bairro = models.CharField(max_length=60, blank=True)
    codigo_municipio = models.CharField("município (código IBGE)", max_length=7, blank=True)
    cep = models.CharField("CEP", max_length=8, blank=True)
    # Endereço no exterior
    pais = models.CharField("país (ISO de 2 letras)", max_length=2, blank=True)
    codigo_postal = models.CharField("código postal", max_length=11, blank=True)
    cidade = models.CharField(max_length=60, blank=True)
    estado = models.CharField("estado ou província", max_length=60, blank=True)

    perfis = models.ManyToManyField(PerfilPessoa, related_name="pessoas", blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "pessoa"
        verbose_name_plural = "pessoas"
        ordering = ["nome", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["documento"],
                condition=~Q(documento=""),
                name="pessoa_documento_unico",
                violation_error_message="Já existe uma pessoa cadastrada com este documento.",
            )
        ]
        indexes = [models.Index(fields=["nome"])]

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()})"

    # --- Validação ---------------------------------------------------------------------

    def clean(self):
        """Normaliza e valida; levanta `ValidationError` com mensagens por campo."""
        erros = {}
        self._validar_identificacao(erros)
        self._validar_contato(erros)
        self._validar_endereco(erros)
        if erros:
            raise ValidationError(erros)

    def _validar_identificacao(self, erros):
        self.nome = (self.nome or "").strip()
        if not self.nome:
            erros["nome"] = "Informe o nome ou a razão social."
        self.nif = (self.nif or "").strip()
        self.inscricao_municipal = (self.inscricao_municipal or "").strip()

        if self.tipo == self.Tipo.PESSOA_FISICA:
            self.documento = normalizar_cpf(self.documento)
            if not cpf_valido(self.documento):
                erros["documento"] = "CPF inválido. Confira os 11 dígitos."
        elif self.tipo == self.Tipo.PESSOA_JURIDICA:
            self.documento = normalizar_cnpj(self.documento)
            if not cnpj_valido(self.documento):
                erros["documento"] = "CNPJ inválido. Confira os 14 caracteres."
        elif self.tipo == self.Tipo.ESTRANGEIRO:
            if (self.documento or "").strip():
                erros["documento"] = "Estrangeiro não tem CPF/CNPJ aqui: informe o NIF."
            self.documento = ""
        else:
            erros["tipo"] = "Escolha pessoa física, pessoa jurídica ou estrangeiro."
            return

        if self.tipo == self.Tipo.ESTRANGEIRO:
            if self.nif and self.motivo_sem_nif is not None:
                erros["motivo_sem_nif"] = (
                    "Informe o NIF ou o motivo de não informá-lo, não os dois."
                )
            elif not self.nif and self.motivo_sem_nif is None:
                erros["nif"] = (
                    "Informe o NIF (número de identificação fiscal no exterior) ou o motivo "
                    "de não informá-lo."
                )
        else:
            if self.nif:
                erros["nif"] = "O NIF é só para estrangeiros."
            if self.motivo_sem_nif is not None:
                erros["motivo_sem_nif"] = "O motivo sem NIF é só para estrangeiros."
        if len(self.inscricao_municipal) > 15:
            erros["inscricao_municipal"] = "A inscrição municipal tem no máximo 15 caracteres."

    def _validar_contato(self, erros):
        telefone = _apenas_digitos(self.telefone)
        if telefone and not 6 <= len(telefone) <= 20:
            erros["telefone"] = "O telefone deve ter de 6 a 20 dígitos."
        self.telefone = telefone

        emails = self.emails_envio if isinstance(self.emails_envio, list) else None
        if emails is None:
            erros["emails_envio"] = "Informe uma lista de e-mails."
            return
        limpos = []
        for item in emails:
            email = str(item).strip().lower()
            try:
                validate_email(email)
            except ValidationError:
                erros["emails_envio"] = f"E-mail inválido: {item}."
                return
            if len(email) > 80:
                erros["emails_envio"] = f"E-mail muito longo (máximo 80 caracteres): {item}."
                return
            if email not in limpos:
                limpos.append(email)
        if len(limpos) > MAXIMO_EMAILS_DE_ENVIO:
            erros["emails_envio"] = f"No máximo {MAXIMO_EMAILS_DE_ENVIO} e-mails de envio."
            return
        self.emails_envio = limpos

    def _validar_endereco(self, erros):
        for campo in ("logradouro", "numero", "complemento", "bairro", "cidade", "estado"):
            setattr(self, campo, (getattr(self, campo) or "").strip())
        self.cep = _apenas_digitos(self.cep)
        self.codigo_municipio = _apenas_digitos(self.codigo_municipio)
        self.pais = (self.pais or "").strip().upper()
        self.codigo_postal = (self.codigo_postal or "").strip()

        tem_nacional = bool(self.codigo_municipio or self.cep)
        tem_exterior = bool(self.pais or self.codigo_postal or self.cidade or self.estado)
        nacional_obrigatorio = self.tipo in (self.Tipo.PESSOA_FISICA, self.Tipo.PESSOA_JURIDICA)

        if tem_nacional and tem_exterior:
            erros["pais"] = "Informe o endereço no Brasil ou no exterior, não os dois."
            return
        if nacional_obrigatorio and tem_exterior:
            erros["pais"] = "Pessoa física ou jurídica nacional tem endereço no Brasil."
            return
        if nacional_obrigatorio or tem_nacional:
            self._exigir_endereco_nacional(erros, nacional_obrigatorio)
        elif tem_exterior or self.logradouro or self.numero or self.bairro:
            self._exigir_endereco_exterior(erros)

    def _exigir_endereco_nacional(self, erros, obrigatorio):
        obrigatorios = {
            "logradouro": "Informe o logradouro.",
            "numero": "Informe o número do endereço.",
            "bairro": "Informe o bairro.",
        }
        for campo, mensagem in obrigatorios.items():
            if not getattr(self, campo):
                erros[campo] = mensagem
        if len(self.cep) != 8:
            erros["cep"] = "Informe o CEP com 8 dígitos."
        if not self.codigo_municipio:
            erros["codigo_municipio"] = (
                "Informe o município do endereço (código IBGE): ele é obrigatório na DPS."
            )
        else:
            try:
                self.codigo_municipio = municipios.validar_codigo_ibge(self.codigo_municipio)
            except ValidationError as erro:
                erros["codigo_municipio"] = erro.messages[0]

    def _exigir_endereco_exterior(self, erros):
        obrigatorios = {
            "logradouro": "Informe o logradouro.",
            "numero": "Informe o número do endereço.",
            "bairro": "Informe o bairro.",
            "codigo_postal": "Informe o código postal.",
            "cidade": "Informe a cidade.",
            "estado": "Informe o estado ou província.",
        }
        for campo, mensagem in obrigatorios.items():
            if not getattr(self, campo):
                erros[campo] = mensagem
        if not re.fullmatch(r"[A-Z]{2}", self.pais):
            erros["pais"] = "Informe o país pelo código ISO de 2 letras (por exemplo, US)."


class ServicoQuerySet(models.QuerySet):
    """Consultas por vigência."""

    def vigentes_em(self, data):
        """Versões ativas cuja vigência cobre a data."""
        return self.filter(ativo=True, vigencia_inicio__lte=data).filter(
            Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=data)
        )

    def vigente(self, data, codigo_tributacao_nacional, codigo_tributacao_municipal=""):
        """Devolve a versão vigente de um serviço (pelos códigos) na data, ou `None`."""
        return (
            self.vigentes_em(data)
            .filter(
                codigo_tributacao_nacional=codigo_tributacao_nacional,
                codigo_tributacao_municipal=codigo_tributacao_municipal,
            )
            .first()
        )


class Servico(models.Model):
    """Serviço prestado, com classificação tributária e **vigência**.

    Cada linha é uma versão do serviço (identificado pelos códigos de tributação) válida de
    `vigencia_inicio` a `vigencia_fim` (aberta se vazia). Versões ativas do mesmo serviço não
    podem se sobrepor; assim, a regra vigente numa data é única (a transição 2026–2033 da
    reforma tributária muda classificações ao longo do tempo).
    """

    nome = models.CharField("nome (uso interno)", max_length=120)
    descricao = models.TextField("descrição na nota", max_length=2000)
    codigo_tributacao_nacional = models.CharField(
        "código de tributação nacional",
        max_length=6,
        help_text="6 dígitos (item, subitem, desdobro).",
    )
    codigo_tributacao_municipal = models.CharField(
        "código de tributação municipal", max_length=3, blank=True
    )
    nbs = models.CharField("NBS", max_length=9, blank=True)
    cst_ibs_cbs = models.CharField("CST do IBS/CBS", max_length=3, blank=True)
    c_class_trib = models.CharField(
        "classificação tributária (cClassTrib)", max_length=6, blank=True
    )

    aliquota_iss = models.DecimalField(
        "alíquota do ISS (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("5"))],
    )
    iss_retido = models.BooleanField("ISS retido pelo tomador", default=False)
    retencao_irrf = models.DecimalField(
        "retenção de IR (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    retencao_csll = models.DecimalField(
        "retenção de CSLL (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    retencao_pis = models.DecimalField(
        "retenção de PIS (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    retencao_cofins = models.DecimalField(
        "retenção de COFINS (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    retencao_inss = models.DecimalField(
        "retenção de INSS (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )

    vigencia_inicio = models.DateField("início da vigência")
    vigencia_fim = models.DateField("fim da vigência", null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = ServicoQuerySet.as_manager()

    CAMPOS_DE_RETENCAO = (
        "retencao_irrf",
        "retencao_csll",
        "retencao_pis",
        "retencao_cofins",
        "retencao_inss",
    )

    class Meta:
        verbose_name = "serviço"
        verbose_name_plural = "serviços"
        ordering = ["nome", "codigo_tributacao_nacional", "-vigencia_inicio"]
        indexes = [
            models.Index(fields=["codigo_tributacao_nacional", "codigo_tributacao_municipal"])
        ]

    def __str__(self):
        return f"{self.nome} ({self.codigo_tributacao_nacional})"

    def clean(self):
        """Normaliza e valida; a sobreposição de vigência fica em `validar_vigencia`."""
        erros = {}
        self.nome = (self.nome or "").strip()
        self.descricao = (self.descricao or "").strip()
        if not self.nome:
            erros["nome"] = "Informe o nome do serviço."
        if not self.descricao:
            erros["descricao"] = "Informe a descrição que sairá na nota."
        elif len(self.descricao) > 2000:
            erros["descricao"] = "A descrição tem no máximo 2000 caracteres."

        self.codigo_tributacao_nacional = _apenas_digitos(self.codigo_tributacao_nacional)
        if len(self.codigo_tributacao_nacional) != 6:
            erros["codigo_tributacao_nacional"] = "O código de tributação nacional tem 6 dígitos."
        self.codigo_tributacao_municipal = _apenas_digitos(self.codigo_tributacao_municipal)
        if self.codigo_tributacao_municipal and (
            len(self.codigo_tributacao_municipal) != 3 or self.codigo_tributacao_municipal == "000"
        ):
            erros["codigo_tributacao_municipal"] = (
                "O código de tributação municipal tem 3 dígitos e não pode ser 000."
            )
        self.nbs = _apenas_digitos(self.nbs)
        if self.nbs and len(self.nbs) != 9:
            erros["nbs"] = "A NBS tem 9 dígitos."
        self.cst_ibs_cbs = _apenas_digitos(self.cst_ibs_cbs)
        self.c_class_trib = _apenas_digitos(self.c_class_trib)
        if self.cst_ibs_cbs and len(self.cst_ibs_cbs) != 3:
            erros["cst_ibs_cbs"] = "O CST do IBS/CBS tem 3 dígitos."
        if self.c_class_trib and len(self.c_class_trib) != 6:
            erros["c_class_trib"] = "A classificação tributária (cClassTrib) tem 6 dígitos."
        if bool(self.cst_ibs_cbs) != bool(self.c_class_trib):
            erros["c_class_trib"] = "Informe o CST e a classificação tributária do IBS/CBS juntos."
        if (self.cst_ibs_cbs or self.c_class_trib) and not self.nbs:
            erros["nbs"] = "A NBS é obrigatória quando há IBS/CBS."

        if self.aliquota_iss is not None and not Decimal("0") <= self.aliquota_iss <= Decimal("5"):
            erros["aliquota_iss"] = "A alíquota do ISS vai de 0% a 5% (LC 116/2003, art. 8º)."
        for campo in self.CAMPOS_DE_RETENCAO:
            valor = getattr(self, campo)
            if valor is not None and not Decimal("0") <= valor <= Decimal("100"):
                erros[campo] = "O percentual de retenção vai de 0% a 100%."

        if self.vigencia_inicio is None:
            erros["vigencia_inicio"] = "Informe o início da vigência."
        elif self.vigencia_fim is not None and self.vigencia_fim < self.vigencia_inicio:
            erros["vigencia_fim"] = "O fim da vigência não pode ser anterior ao início."
        if erros:
            raise ValidationError(erros)

    def validar_vigencia(self):
        """Recusa a versão se a vigência se sobrepõe a outra ativa do mesmo serviço."""
        if not self.ativo:
            return
        concorrentes = Servico.objects.filter(
            ativo=True,
            codigo_tributacao_nacional=self.codigo_tributacao_nacional,
            codigo_tributacao_municipal=self.codigo_tributacao_municipal,
        ).exclude(pk=self.pk)
        if self.vigencia_fim is not None:
            concorrentes = concorrentes.filter(vigencia_inicio__lte=self.vigencia_fim)
        concorrentes = concorrentes.filter(
            Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=self.vigencia_inicio)
        )
        conflito = concorrentes.order_by("vigencia_inicio").first()
        if conflito is not None:
            fim = conflito.vigencia_fim.strftime("%d/%m/%Y") if conflito.vigencia_fim else "aberta"
            raise ValidationError(
                {
                    "vigencia_inicio": (
                        "A vigência se sobrepõe à versão de "
                        f"{conflito.vigencia_inicio:%d/%m/%Y} até {fim} deste serviço. "
                        "Encerre a versão anterior antes de cadastrar a nova."
                    )
                }
            )
