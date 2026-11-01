"""Instalação nativa: systemd + Nginx + Gunicorn + worker + beat (sem Docker)."""

import os
from pathlib import Path

from freenfse_instalador import segredos, tls
from freenfse_instalador.base import Instalacao

PORTA_INTERNA = 8000
FORMATO_DO_ACESSO = (
    '{"ts":"%(t)s","ip":"%(h)s","metodo":"%(m)s","caminho":"%(U)s",'
    '"status":%(s)s,"bytes":%(b)s,"ms":%(M)s}'
)
ENDURECIMENTO = """\
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
"""
PROXY_NATIVO = """\
# Repasse ao Gunicorn local; gerado pelo instalador.
proxy_pass http://127.0.0.1:8000;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $proto_encaminhado;
proxy_read_timeout 120s;
proxy_hide_header X-Content-Type-Options;
proxy_hide_header Referrer-Policy;
proxy_hide_header X-Frame-Options;
"""


def _escapar_systemd(texto):
    """No systemd, `%` é especificador: para o Gunicorn receber `%(t)s` é preciso `%%(t)s`."""
    return texto.replace("%", "%%")


class InstalacaoNativa(Instalacao):
    """Cria usuário, venv, banco, unidades systemd e o site do Nginx."""

    # -- caminhos --------------------------------------------------------------------------

    @property
    def venv(self):
        """Ambiente virtual do Python."""
        return Path(self.p.dados) / "venv"

    @property
    def www(self):
        """Arquivos estáticos do frontend."""
        return Path(self.p.dados) / "www"

    @property
    def pasta_erros(self):
        """Páginas de erro do Nginx."""
        return Path(self.p.dados) / "erros"

    @property
    def pasta_letsencrypt(self):
        """Onde o certbot guarda os certificados."""
        return Path(self.p.extras.get("pasta_letsencrypt", "/etc/letsencrypt"))

    def valores_do_modo(self):
        """Banco e Redis locais, pastas de dados e o cabeçalho do IP real (escrito pelo Nginx)."""
        dados = Path(self.p.dados)
        return {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "REDIS_URL": "redis://localhost:6379/0",
            "FREENFSE_EXPORTACOES_DIR": str(dados / "exportacoes"),
            "FREENFSE_BACKUP_DIR": str(dados / "backups"),
            "IP_CABECALHO_CONFIAVEL": "X-Real-IP",
            "DEBUG": "false",
        }

    def comando_manage(self, *args, ambiente=None):
        """`manage.py` do venv, como o usuário do serviço, com o `.env` lido pelo instalador."""
        env = {**self._env_do_servico(), **(ambiente or {})}
        return [str(self.venv / "bin" / "python"), "manage.py", *args], env

    def _env_do_servico(self):
        valores = segredos.ler_env(self.p.env) if self.p.env.is_file() else {}
        return {**os.environ, **valores}

    # -- arquivos --------------------------------------------------------------------------

    def unidade(self, nome, descricao, comando, *, extra=""):
        """Texto de uma unidade systemd do serviço."""
        p = self.p
        return (
            f"[Unit]\nDescription=freenfse - {descricao}\n"
            "After=network-online.target postgresql.service redis-server.service\n"
            "Wants=network-online.target\n\n"
            "[Service]\nType=simple\n"
            f"User={p.usuario_do_servico}\nGroup={p.usuario_do_servico}\n"
            f"WorkingDirectory={p.repositorio}/backend\n"
            f"EnvironmentFile={p.env}\n"
            f"ExecStart={_escapar_systemd(comando)}\n"
            "Restart=on-failure\nRestartSec=5\n"
            f"{ENDURECIMENTO}ReadWritePaths={p.dados}\n{extra}\n"
            "[Install]\nWantedBy=multi-user.target\n"
        )

    def unidades(self):
        """As três unidades: web (Gunicorn), worker e beat do Celery."""
        bin_ = self.venv / "bin"
        web = (
            f"{bin_}/gunicorn config.wsgi:application --bind 127.0.0.1:{PORTA_INTERNA} "
            f"--workers 2 --access-logfile - --access-logformat '{FORMATO_DO_ACESSO}' "
            "--no-control-socket"
        )
        return {
            "freenfse-web.service": self.unidade("web", "API (Gunicorn)", web),
            "freenfse-worker.service": self.unidade(
                "worker",
                "worker do Celery",
                f"{bin_}/celery -A config worker --loglevel=info --concurrency=2",
            ),
            "freenfse-beat.service": self.unidade(
                "beat",
                "agendador do Celery (beat)",
                f"{bin_}/celery -A config beat --loglevel=info "
                "--schedule=/run/freenfse/celerybeat-schedule",
                extra="RuntimeDirectory=freenfse\n",
            ),
        }

    def nginx_http(self):
        """Servidor HTTP (porta pedida): SPA, API e desafio ACME."""
        p = self.p
        return (
            "# Gerado pelo instalador do freenfse.\n"
            "map $scheme $proto_encaminhado {\n    default $scheme;\n}\n\n"
            "server {\n"
            f"    listen {p.porta_http};\n    server_name {p.dominio};\n\n"
            f"    root {self.www};\n    index index.html;\n\n"
            "    location /.well-known/acme-challenge/ {\n"
            f"        root {p.dados}/certbot-www;\n    }}\n\n"
            "    location /erros/ {\n"
            f"        internal;\n        alias {self.pasta_erros}/;\n    }}\n\n"
            "    include /etc/nginx/freenfse/locais.conf;\n}\n"
        )

    def nginx_tls(self):
        """Servidor HTTPS a partir do modelo compartilhado com o Compose."""
        p = self.p
        if p.tls == "letsencrypt":
            certificado, chave = tls.caminhos_letsencrypt(p.dominio, str(self.pasta_letsencrypt))
        else:
            certificado = str(Path(p.dados) / "certificados" / "fullchain.pem")
            chave = str(Path(p.dados) / "certificados" / "privkey.pem")
        return tls.renderizar_nginx_tls(
            p.repositorio / "docker" / "nginx" / "tls.conf.modelo",
            dominio=p.dominio,
            certificado=certificado,
            chave=chave,
            raiz=str(self.www),
            erros=str(self.pasta_erros),
        ).replace(f"root {tls.RAIZ_ACME};", f"root {p.dados}/certbot-www;")

    @property
    def pasta_bin(self):
        """Onde fica o atalho `freenfse-manage`."""
        return Path(self.p.extras.get("pasta_bin", "/usr/local/bin"))

    def gravar_nginx(self, *, com_tls):
        """Escreve os arquivos do Nginx e valida a sintaxe antes de recarregar."""
        p = self.p
        base = Path(p.pasta_nginx)
        locais = (
            "" if p.simular else (p.repositorio / "docker/nginx/locais.conf").read_text("utf-8")
        )
        self.gravar(base / "freenfse" / "locais.conf", locais)
        self.gravar(base / "freenfse" / "proxy.conf", PROXY_NATIVO)
        self.gravar(
            base / "conf.d" / "freenfse.conf", self.nginx_tls() if com_tls else self.nginx_http()
        )
        self.executar(["nginx", "-t"])
        self.executar(["systemctl", "reload", "nginx"])

    def script_manage(self):
        """Atalho `freenfse-manage` para rodar o `manage.py` no ambiente certo."""
        p = self.p
        return (
            "#!/bin/sh\n# Roda o manage.py do freenfse no ambiente do serviço.\n"
            "# Uso: freenfse-manage <comando>\n"
            f"set -eu\nset -a\n. {p.env}\nset +a\ncd {p.repositorio}/backend\n"
            f'exec runuser -u {p.usuario_do_servico} -- {self.venv}/bin/python manage.py "$@"\n'
        )

    # -- etapas ----------------------------------------------------------------------------

    def verificar_prerequisitos(self):
        """Python 3.14, PostgreSQL, Redis, Nginx, git, age e Node (ou frontend pronto)."""
        p = self.p
        self.passo("Pré-requisitos")
        necessarios = {
            p.python: "Python 3.14 (ex.: via uv ou pyenv; o Ubuntu/Debian ainda não o trazem)",
            "psql": "PostgreSQL 18 (pacote postgresql-18 do repositório PGDG)",
            "pg_dump": "o cliente do PostgreSQL 18 (postgresql-client-18)",
            "redis-cli": "Redis (pacote redis-server)",
            "nginx": "Nginx (pacote nginx)",
            "git": "git (a biblioteca fiscal é instalada por commit)",
            "age": "age (pacote age; cifra os backups)",
            "systemctl": "systemd",
        }
        if not p.frontend_pronto:
            necessarios["npm"] = "Node.js 22 com npm (ou use --frontend-pronto com a pasta dist)"
        if p.tls == "letsencrypt":
            necessarios["certbot"] = "certbot (pacote certbot)"
        faltando = [
            f"{prog}: {como}"
            for prog, como in necessarios.items()
            if not self.executor.existe(prog)
        ]
        if faltando and not p.simular:
            raise RuntimeError("Faltam no servidor:\n  - " + "\n  - ".join(faltando))
        for linha in faltando:
            self.aviso(f"(simulação) faltaria: {linha}")

    def preparar_usuario_e_pastas(self):
        """Usuário de sistema do serviço e pastas de dados."""
        p = self.p
        dados = Path(p.dados)
        self.passo("Usuário e pastas")
        if self.executar(["id", "-u", p.usuario_do_servico], verificar=False).codigo != 0:
            self.executar(
                [
                    "useradd",
                    "--system",
                    "--home-dir",
                    str(dados),
                    "--shell",
                    "/usr/sbin/nologin",
                    p.usuario_do_servico,
                ]
            )
        dono = f"{p.usuario_do_servico}:{p.usuario_do_servico}"
        for nome, modo in (
            ("", 0o755),
            ("backups", 0o700),
            ("exportacoes", 0o750),
            ("www", 0o755),
            ("erros", 0o755),
            ("certbot-www", 0o755),
        ):
            self.criar_pasta(
                dados / nome if nome else dados,
                modo=modo,
                dono=dono if nome in ("", "backups", "exportacoes") else None,
            )
        if p.tls == "proprio":
            self.criar_pasta(dados / "certificados", modo=0o755)

    def preparar_banco(self):
        """Papel e banco do PostgreSQL (idempotente); a senha chega como verificador SCRAM."""
        env = self.segredos
        self.passo("Banco de dados")
        existe = self.executar(
            [
                "runuser",
                "-u",
                "postgres",
                "--",
                "psql",
                "-tAc",
                "SELECT 1 FROM pg_roles WHERE rolname = 'freenfse'",
            ],
            verificar=False,
        )
        papel_existe = existe.saida.strip() == "1"
        if not papel_existe or "POSTGRES_PASSWORD" in self.gerados:
            verbo = "ALTER" if papel_existe else "CREATE"
            verificador = segredos.verificador_scram(env.get("POSTGRES_PASSWORD", ""))
            self.executar(
                ["runuser", "-u", "postgres", "--", "psql", "-v", "ON_ERROR_STOP=1"],
                entrada=f"{verbo} ROLE freenfse WITH LOGIN PASSWORD '{verificador}';\n",
            )
        banco = self.executar(
            [
                "runuser",
                "-u",
                "postgres",
                "--",
                "psql",
                "-tAc",
                "SELECT 1 FROM pg_database WHERE datname = 'freenfse'",
            ],
            verificar=False,
        )
        if banco.saida.strip() != "1":
            self.executar(
                ["runuser", "-u", "postgres", "--", "createdb", "-O", "freenfse", "freenfse"]
            )

    def instalar_aplicacao(self):
        """Venv, dependências, frontend e migrações."""
        p = self.p
        self.passo("Aplicação")
        if not (self.venv / "bin" / "python").exists() or p.simular:
            self.executar([p.python, "-m", "venv", str(self.venv)])
        self.executar(
            [
                str(self.venv / "bin" / "pip"),
                "install",
                "-r",
                str(p.repositorio / "backend" / "requirements.txt"),
            ],
            longo=True,
        )
        if p.frontend_pronto:
            self.executar(["cp", "-r", f"{p.frontend_pronto}/.", str(self.www)])
        else:
            self.executar(
                ["npm", "ci", "--no-audit", "--no-fund"],
                cwd=str(p.repositorio / "frontend"),
                longo=True,
            )
            self.executar(["npm", "run", "build"], cwd=str(p.repositorio / "frontend"), longo=True)
            self.executar(["cp", "-r", f"{p.repositorio}/frontend/dist/.", str(self.www)])
        self.executar(["cp", "-r", f"{p.repositorio}/docker/erros/.", str(self.pasta_erros)])
        usuario = p.usuario_do_servico
        for args in (
            ("migrate_schemas", "--noinput"),
            ("carregar_municipios",),
            ("atualizar_views_bi", "--se-existir"),
        ):
            comando, env = self.comando_manage(*args)
            self.executar(comando, env=env, cwd=str(p.repositorio / "backend"), usuario=usuario)

    def instalar_servicos(self):
        """Grava as unidades systemd e liga os serviços."""
        p = self.p
        self.passo("Serviços (systemd)")
        for nome, texto in self.unidades().items():
            self.gravar(Path(p.pasta_systemd) / nome, texto)
        self.gravar(self.pasta_bin / "freenfse-manage", self.script_manage(), modo=0o750)
        self.executar(["systemctl", "daemon-reload"])
        self.executar(["systemctl", "enable", "--now", *self.unidades()])

    def configurar_tls(self):
        """HTTPS: certbot (webroot) ou o certificado informado."""
        p = self.p
        if not p.https:
            return
        self.passo("HTTPS")
        if p.tls == "proprio":
            destino = Path(p.dados) / "certificados"
            self.gravar(
                destino / "fullchain.pem",
                "" if p.simular else Path(p.certificado).read_text(encoding="utf-8"),
                modo=0o644,
            )
            self.gravar(
                destino / "privkey.pem",
                "" if p.simular else Path(p.chave_privada).read_text(encoding="utf-8"),
                modo=0o640,
            )
        else:
            if (
                not (self.pasta_letsencrypt / "live" / p.dominio / "fullchain.pem").exists()
                or p.simular
            ):
                self.executar(
                    tls.comando_certbot_nativo(
                        dominio=p.dominio, email=p.email, pasta_acme=Path(p.dados) / "certbot-www"
                    ),
                    longo=True,
                )
            self.gravar(
                self.pasta_letsencrypt / "renewal-hooks" / "deploy" / "freenfse-nginx",
                "#!/bin/sh\nsystemctl reload nginx\n",
                modo=0o755,
            )
        self.gravar_nginx(com_tls=True)

    # -- fluxo ---------------------------------------------------------------------------------

    def instalar(self):
        """Instala (ou atualiza) tudo, sem trocar nenhum segredo existente."""
        p = self.p
        self.passo(f"Instalação nativa — {p.url}")
        self.verificar_prerequisitos()
        self.reaproveitar_configuracao()
        self.preparar_usuario_e_pastas()
        self.passo("Configuração (.env)")
        self.preparar_chave_de_backup()
        self.preparar_env()
        self.preparar_banco()
        self.instalar_aplicacao()
        self.gravar_nginx(com_tls=False)  # HTTP primeiro: o desafio do Let's Encrypt precisa dele
        self.instalar_servicos()
        self.configurar_tls()
        self.passo("Pós-instalação")
        self.criar_master()
        self.criar_usuario_bi()
        self.passo("Verificação final")
        corpo = self.verificar_saude()
        self.resumo(corpo)
        return corpo
