"""Cópia de cadastros de pessoas entre empresas (operação explícita; não cria vínculo)."""

from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context

from cadastros.models import PerfilPessoa, Pessoa
from core.models import LogAuditoria
from core.services import acesso, auditoria

CAMPOS_COPIADOS = (
    "tipo",
    "documento",
    "nif",
    "motivo_sem_nif",
    "nome",
    "inscricao_municipal",
    "telefone",
    "emails_envio",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "codigo_municipio",
    "cep",
    "pais",
    "codigo_postal",
    "cidade",
    "estado",
    "ativo",
)


class SemAcessoAOrigem(Exception):
    """O usuário não tem vínculo ativo (ou permissão de leitura) na empresa de origem."""


class CopiaInvalida(Exception):
    """Pedido de cópia inválido (por exemplo, origem igual ao destino)."""


def _exigir_leitura_na_origem(usuario, empresa_origem):
    resolvido = acesso.acesso_a_empresa(usuario, empresa_origem)
    if resolvido is None or "cadastro.consultar" not in resolvido[2]:
        raise SemAcessoAOrigem


def listar_da_origem(*, usuario, empresa_origem, empresa_destino, busca=""):
    """Pessoas da empresa de origem que o usuário pode copiar (leitura na origem)."""
    if empresa_origem.pk == empresa_destino.pk:
        raise CopiaInvalida("Escolha uma empresa diferente da empresa ativa.")
    _exigir_leitura_na_origem(usuario, empresa_origem)
    with schema_context(empresa_origem.schema_name):
        consulta = Pessoa.objects.filter(ativo=True).order_by("nome", "id")
        if busca:
            consulta = consulta.filter(nome__icontains=busca)
        return [
            {
                "id": pessoa.pk,
                "tipo": pessoa.tipo,
                "documento": pessoa.documento,
                "nome": pessoa.nome,
            }
            for pessoa in consulta[:500]
        ]


def copiar_pessoas(*, request, empresa_origem, empresa_destino, ids=None):
    """Copia pessoas da origem para o destino (empresa ativa da requisição).

    Exige leitura de cadastros na origem — vínculo ativo, ou Master — e, no destino,
    `cadastro.editar` (verificado pela view). É **cópia**: depois dela os registros são
    independentes. Pessoas cujo documento (ou NIF) já existe no destino são ignoradas, e cada
    ignorada vem com o motivo. Registra na auditoria quantas foram copiadas, sem dados pessoais.
    """
    if empresa_origem.pk == empresa_destino.pk:
        raise CopiaInvalida("A origem e o destino são a mesma empresa.")
    _exigir_leitura_na_origem(request.user, empresa_origem)

    with schema_context(empresa_origem.schema_name):
        consulta = Pessoa.objects.prefetch_related("perfis").order_by("nome", "id")
        if ids is not None:
            consulta = consulta.filter(pk__in=ids)
        pessoas = [
            (
                {campo: getattr(pessoa, campo) for campo in CAMPOS_COPIADOS},
                [(perfil.codigo, perfil.nome) for perfil in pessoa.perfis.all()],
                pessoa.pk,
            )
            for pessoa in consulta
        ]

    copiadas, ignoradas = 0, []
    with schema_context(empresa_destino.schema_name):
        for dados, perfis, origem_id in pessoas:
            motivo = _motivo_para_ignorar(dados)
            if motivo is None:
                nova = Pessoa(**dados)
                try:
                    nova.clean()
                except ValidationError as erro:
                    motivo = "; ".join(m for lista in erro.message_dict.values() for m in lista)
                else:
                    nova.save()
                    nova.perfis.set(_perfis_do_destino(perfis))
                    copiadas += 1
                    continue
            ignoradas.append({"id": origem_id, "nome": dados["nome"], "motivo": motivo})

    auditoria.registrar(
        LogAuditoria.Acao.PESSOAS_COPIADAS,
        request=request,
        alvo=f"pessoas:{empresa_origem.cnpj}->{empresa_destino.cnpj}",
        detalhes={
            "origem": empresa_origem.pk,
            "destino": empresa_destino.pk,
            "copiadas": copiadas,
            "ignoradas": len(ignoradas),
        },
    )
    return {"copiadas": copiadas, "ignoradas": ignoradas}


def _motivo_para_ignorar(dados):
    """Motivo para não copiar a pessoa, ou `None` se pode copiar."""
    if dados["documento"] and Pessoa.objects.filter(documento=dados["documento"]).exists():
        return "Já existe uma pessoa com este documento na empresa de destino."
    if dados["nif"] and Pessoa.objects.filter(nif=dados["nif"], tipo=dados["tipo"]).exists():
        return "Já existe um estrangeiro com este NIF na empresa de destino."
    return None


def _perfis_do_destino(perfis):
    """Perfis do destino com os mesmos códigos; cria os que a empresa de destino ainda não tem."""
    return [
        PerfilPessoa.objects.get_or_create(codigo=codigo, defaults={"nome": nome})[0]
        for codigo, nome in perfis
    ]
