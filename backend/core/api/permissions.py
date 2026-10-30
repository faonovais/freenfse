"""Classes de permissão do DRF."""

from rest_framework.permissions import BasePermission


class PermissaoPorOperacao(BasePermission):
    """Exige a permissão nomeada declarada para a operação, no vínculo da empresa da requisição.

    A view declara `permissao_requerida`, um dicionário `{operação: "recurso.acao"}`.
    Em `ViewSet` a operação é o nome da ação (`list`, `create`, `cancelar`…); em
    `APIView`, o método HTTP em minúsculas (`get`, `post`…). **Falha fechada**: uma
    operação sem permissão declarada é negada. Só vale em rota de empresa, onde o
    middleware define `request.empresa` e `request.permissoes`.
    """

    def has_permission(self, request, view):
        """Concede acesso se a permissão exigida está entre as efetivas do usuário."""
        if not request.user.is_authenticated or getattr(request, "empresa", None) is None:
            return False
        operacao = getattr(view, "action", None) or request.method.lower()
        requerida = (getattr(view, "permissao_requerida", None) or {}).get(operacao)
        return requerida is not None and requerida in request.permissoes


class PermissaoMaster(BasePermission):
    """Restringe a rota ao papel Master (administração global)."""

    def has_permission(self, request, view):
        """Só o Master autenticado e ativo."""
        usuario = request.user
        return bool(usuario.is_authenticated and usuario.is_active and usuario.is_master)
