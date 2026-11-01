"""Instalação por Docker Compose (servidor interno, VPS ou nuvem com Docker)."""

import os
from pathlib import Path

from freenfse_instalador import tls
from freenfse_instalador.base import Instalacao

UID_DO_SERVICO = "10001:10001"  # usuário freenfse dentro da imagem do backend
ARQUIVO_OVERRIDE = "docker-compose.instalacao.yml"


class InstalacaoCompose(Instalacao):
    """Gera um override do Compose (sem segredos), sobe a pilha e configura o HTTPS."""

    # -- comandos --------------------------------------------------------------------------

    @property
    def override(self):
        """Caminho do override gerado."""
        return self.p.repositorio / ARQUIVO_OVERRIDE

    def compose(self, *args):
        """`docker compose` com o arquivo base, o override e o `.env` desta instalação."""
        return [
            "docker", "compose",
            "--env-file", str(self.p.env),
            "-f", str(self.p.repositorio / "docker-compose.yml"),
            "-f", str(self.override),
            *args,
        ]  # fmt: skip

    def comando_manage(self, *args, ambiente=None):
        """`docker compose exec backend python manage.py ...`; segredos só por ambiente."""
        env = None
        passagem = []
        if ambiente:
            env = {**os.environ, **ambiente}
            for nome in ambiente:
                passagem += ["-e", nome]  # só o nome: o valor vem do ambiente do processo
        comando = self.compose("exec", "-T", *passagem, "backend", "python", "manage.py", *args)
        return comando, env

    # -- arquivos --------------------------------------------------------------------------

    def renderizar_override(self, *, com_tls):
        """Override do Compose: backups no disco do host, ACME e (opcional) HTTPS no Nginx."""
        p = self.p
        dados = Path(p.dados)
        linhas = [
            "# Gerado pelo instalador do freenfse. Não contém segredos; pode ser regerado.",
            "services:",
        ]
        for servico in ("backend", "worker"):
            linhas += [
                f"  {servico}:",
                "    volumes:",
                f'      - "{dados}/backups:/var/lib/freenfse/backups"',
            ]
        linhas += ["  nginx:", "    volumes:", f'      - "{dados}/certbot-www:{tls.RAIZ_ACME}"']
        if com_tls:
            origem_cert = (
                f"{dados}/letsencrypt:/etc/letsencrypt:ro"
                if p.tls == "letsencrypt"
                else f"{dados}/certificados:/etc/ssl/freenfse:ro"
            )
            linhas += [
                f'      - "{dados}/nginx/tls.conf:/etc/nginx/conf.d/default.conf:ro"',
                f'      - "{origem_cert}"',
                "    ports:",
                '      - "${HTTPS_PORT:-443}:443"',
            ]
        return "\n".join(linhas) + "\n"

    def gravar_override(self, *, com_tls):
        """Grava o override (sem segredos)."""
        self.gravar(self.override, self.renderizar_override(com_tls=com_tls))

    def gravar_nginx_tls(self):
        """Renderiza a configuração HTTPS do Nginx para dentro da pasta de dados."""
        p = self.p
        if p.tls == "letsencrypt":
            certificado, chave = tls.caminhos_letsencrypt(p.dominio)
        else:
            certificado, chave = "/etc/ssl/freenfse/fullchain.pem", "/etc/ssl/freenfse/privkey.pem"
        texto = tls.renderizar_nginx_tls(
            p.repositorio / "docker" / "nginx" / "tls.conf.modelo",
            dominio=p.dominio,
            certificado=certificado,
            chave=chave,
            raiz="/usr/share/nginx/html",
            erros="/usr/share/nginx/erros",
        )
        self.gravar(Path(p.dados) / "nginx" / "tls.conf", texto)

    # -- etapas ----------------------------------------------------------------------------

    def verificar_prerequisitos(self):
        """Docker e o plugin Compose."""
        self.passo("Pré-requisitos")
        faltando = []
        if not self.executor.existe("docker"):
            faltando.append("Docker (https://docs.docker.com/engine/install/)")
        else:
            if self.executar(["docker", "compose", "version"], verificar=False).codigo != 0:
                faltando.append("o plugin Docker Compose v2 (pacote docker-compose-plugin)")
        if self.p.gerar_chave_backup and not self.executor.existe("age-keygen"):
            faltando.append("o age (pacote 'age') para gerar a chave de backup")
        if faltando and not self.p.simular:
            raise RuntimeError("Faltam no servidor: " + "; ".join(faltando))

    def preparar_pastas(self):
        """Pastas de dados: backups (dono do serviço, só ele lê), ACME e certificados."""
        dados = Path(self.p.dados)
        self.passo("Pastas de dados")
        self.criar_pasta(dados, modo=0o755)
        self.criar_pasta(dados / "backups", modo=0o700, dono=UID_DO_SERVICO)
        self.criar_pasta(dados / "certbot-www", modo=0o755)
        self.criar_pasta(dados / "nginx", modo=0o755)
        if self.p.tls == "letsencrypt":
            self.criar_pasta(dados / "letsencrypt", modo=0o755)
        if self.p.tls == "proprio":
            self.criar_pasta(dados / "certificados", modo=0o755)

    def copiar_certificado_proprio(self):
        """Copia o certificado e a chave para a pasta de dados (chave só legível pelo dono)."""
        if self.p.tls != "proprio":
            return
        destino = Path(self.p.dados) / "certificados"
        self.gravar(
            destino / "fullchain.pem",
            "" if self.p.simular else Path(self.p.certificado).read_text(encoding="utf-8"),
            modo=0o644,
        )
        # A chave precisa ser legível pelo usuário do Nginx dentro do contêiner.
        self.gravar(
            destino / "privkey.pem",
            "" if self.p.simular else Path(self.p.chave_privada).read_text(encoding="utf-8"),
            modo=0o640,
        )

    def subir(self):
        """Sobe (ou atualiza) a pilha e espera os serviços ficarem saudáveis."""
        self.passo("Subindo os serviços (isto pode levar alguns minutos na primeira vez)")
        self.executar(
            self.compose("up", "-d", "--build", "--wait", "--wait-timeout", "600"), longo=True
        )

    def configurar_letsencrypt(self):
        """Obtém o certificado (se ainda não há) e troca o Nginx para a configuração HTTPS."""
        p = self.p
        dados = Path(p.dados)
        self.passo("HTTPS com Let's Encrypt")
        existente = dados / "letsencrypt" / "live" / p.dominio / "fullchain.pem"
        if existente.exists() and not p.simular:
            self.dizer("  Certificado já existe: será reaproveitado.")
        else:
            self.executar(
                tls.comando_certbot_docker(
                    dominio=p.dominio,
                    email=p.email,
                    pasta_letsencrypt=str(dados / "letsencrypt"),
                    pasta_acme=str(dados / "certbot-www"),
                ),
                longo=True,
            )
        self.gravar_nginx_tls()
        self.gravar_override(com_tls=True)
        self.executar(self.compose("up", "-d", "nginx"))
        self.gravar_renovacao()

    def gravar_renovacao(self):
        """Script de renovação + agendamento diário (se for root)."""
        dados = Path(self.p.dados)
        script = dados / "renovar-certificado.sh"
        texto = tls.script_de_renovacao_docker(
            pasta_letsencrypt=str(dados / "letsencrypt"),
            pasta_acme=str(dados / "certbot-www"),
            comando_compose=self.compose(),
        )
        self.gravar(script, texto, modo=0o755)
        if self.p.simular or os.geteuid() != 0:
            self.aviso(
                f"Agende a renovação do certificado (duas vezes por dia): {script} "
                "(ex.: crontab -e → 17 3,15 * * * " + str(script) + ")"
            )
            return
        self.gravar(
            Path("/etc/cron.d/freenfse-certificado"),
            f"17 3,15 * * * root {script} >/dev/null 2>&1\n",
            modo=0o644,
        )

    # -- fluxo ---------------------------------------------------------------------------------

    def instalar(self):
        """Instala (ou atualiza) tudo, na ordem certa e sem trocar nenhum segredo existente."""
        p = self.p
        self.passo(f"Instalação por Docker Compose — {p.url}")
        self.verificar_prerequisitos()
        self.reaproveitar_configuracao()
        self.preparar_pastas()
        self.passo("Configuração (.env)")
        self.preparar_chave_de_backup()
        self.preparar_env()
        if p.tls == "proprio":
            self.copiar_certificado_proprio()
        # Com Let's Encrypt, a primeira subida é só HTTP (para o desafio); o HTTPS vem depois.
        certificado_pronto = (
            Path(p.dados) / "letsencrypt" / "live" / p.dominio / "fullchain.pem"
        ).exists()
        com_tls_ja = p.tls == "proprio" or (p.tls == "letsencrypt" and certificado_pronto)
        if com_tls_ja:
            self.gravar_nginx_tls()
        self.gravar_override(com_tls=com_tls_ja)
        self.subir()
        if p.tls == "letsencrypt" and not com_tls_ja:
            self.configurar_letsencrypt()
        elif p.tls == "letsencrypt":
            self.gravar_renovacao()
        self.passo("Pós-instalação")
        self.criar_master()
        self.criar_usuario_bi()
        self.passo("Verificação final")
        corpo = self.verificar_saude()
        self.resumo(corpo)
        return corpo
