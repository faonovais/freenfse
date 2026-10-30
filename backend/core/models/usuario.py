"""Usuário do sistema (schema público)."""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class UsuarioManager(BaseUserManager):
    """Cria usuários identificados pelo e-mail (sem nome de usuário)."""

    use_in_migrations = True

    def _criar(self, email, password, **extra):
        email = self.normalize_email(email or "").strip().lower()
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        usuario = self.model(email=email, **extra)
        if password:
            usuario.set_password(password)
        else:
            usuario.set_unusable_password()
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        """Cria um usuário comum (sem papel Master)."""
        extra.setdefault("is_master", False)
        return self._criar(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        """Cria um usuário Master (papel global, D22)."""
        extra["is_master"] = True
        return self._criar(email, password, **extra)


class Usuario(AbstractBaseUser):
    """Pessoa que acessa o sistema.

    Não guarda empresa nem perfil: o acesso a cada empresa é o
    `VinculoUsuarioEmpresa` (D10). `is_master` é o papel global (D22), fora dos
    perfis de empresa.
    """

    email = models.EmailField("e-mail", max_length=254, unique=True)
    nome = models.CharField("nome", max_length=150, blank=True)
    is_active = models.BooleanField("ativo", default=True)
    is_master = models.BooleanField("Master", default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["email"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        """Normaliza o e-mail (minúsculas, sem espaços) antes de gravar."""
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    def get_full_name(self):
        """Nome para exibição."""
        return self.nome or self.email

    def get_short_name(self):
        """Primeiro nome, ou o e-mail se não houver nome."""
        return (self.nome.split(" ")[0] if self.nome else self.email).strip()
