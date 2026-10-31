"""Middlewares de acesso: 2FA obrigatório e empresa ativa por requisição (D10).

A empresa ativa vem **somente** do cabeçalho `X-Empresa` de cada requisição,
validada contra o vínculo do usuário. Nunca é lida da sessão: com duas abas
abertas, trocar de empresa numa delas faria a outra emitir no CNPJ errado.
"""

from django.db import connection
from django.http import JsonResponse

from core.models import Empresa, LogAuditoria
from core.services import acesso, auditoria

# Rotas que não pertencem a uma empresa: públicas, do usuário logado e de administração global.
PREFIXOS_SEM_EMPRESA = (
    "/api/versao/",
    "/api/eu/",
    "/api/admin-global/",
    "/_allauth/",
    "/accounts/",
)
# Rotas liberadas mesmo quando o 2FA é obrigatório e ainda não foi configurado: as
# necessárias para configurá-lo e saber o estado.
PREFIXOS_SEM_2FA = ("/api/versao/", "/api/eu/", "/_allauth/", "/accounts/")


def _erro(status, codigo, detalhe):
    return JsonResponse({"codigo": codigo, "detalhe": detalhe}, status=status)


def rota_exige_empresa(caminho):
    """Toda rota da API fora das listas públicas e de administração global é de empresa."""
    return caminho.startswith("/api/") and not caminho.startswith(PREFIXOS_SEM_EMPRESA)


class Exigir2FAMiddleware:
    """Bloqueia a API para quem deve ter 2FA e ainda não o configurou (política em settings)."""

    def __init__(self, get_response):
        """Guarda o próximo elo da cadeia de middlewares."""
        self.get_response = get_response

    def __call__(self, request):
        """Responde 403 `2fa_obrigatorio` até o usuário ativar o 2FA."""
        usuario = request.user
        if (
            request.path.startswith("/api/")
            and not request.path.startswith(PREFIXOS_SEM_2FA)
            and usuario.is_authenticated
            and acesso.exige_2fa(usuario)
            and not acesso.usuario_tem_2fa(usuario)
        ):
            return _erro(
                403,
                "2fa_obrigatorio",
                "Configure a verificação em duas etapas para continuar.",
            )
        return self.get_response(request)


class EmpresaPorCabecalhoMiddleware:
    """Ativa o schema da empresa indicada em `X-Empresa`, após validar o acesso do usuário.

    Disponibiliza `request.empresa`, `request.vinculo`, `request.perfil` e
    `request.permissoes`. O schema volta para o público ao fim de toda requisição.
    """

    def __init__(self, get_response):
        """Guarda o próximo elo da cadeia de middlewares."""
        self.get_response = get_response

    def __call__(self, request):
        """Resolve a empresa (se a rota for de empresa) e processa a requisição."""
        connection.set_schema_to_public()
        request.empresa = None
        request.vinculo = None
        request.perfil = None
        request.permissoes = frozenset()
        try:
            if rota_exige_empresa(request.path):
                negado = self._ativar_empresa(request)
                if negado is not None:
                    return negado
            return self.get_response(request)
        finally:
            connection.set_schema_to_public()

    def _ativar_empresa(self, request):
        usuario = request.user
        if not usuario.is_authenticated:
            return _erro(401, "nao_autenticado", "Faça login para continuar.")

        bruto = request.headers.get("X-Empresa", "").strip()
        if not bruto:
            return _erro(400, "empresa_nao_informada", "Informe a empresa no cabeçalho X-Empresa.")
        if not bruto.isdigit():
            return _erro(
                400, "empresa_invalida", "O cabeçalho X-Empresa deve ser o número da empresa."
            )

        empresa = Empresa.objects.filter(pk=int(bruto)).first()
        resolvido = acesso.acesso_a_empresa(usuario, empresa) if empresa else None
        if resolvido is None:
            # Mesma resposta para empresa inexistente e sem vínculo: não revela quais existem.
            auditoria.registrar(
                LogAuditoria.Acao.ACESSO_NEGADO,
                request=request,
                alvo=f"Empresa:{bruto}",
                detalhes={"rota": request.path},
            )
            return _erro(403, "sem_acesso_a_empresa", "Você não tem acesso a esta empresa.")

        request.vinculo, request.perfil, request.permissoes = resolvido
        request.empresa = empresa
        connection.set_tenant(empresa)
        return None
