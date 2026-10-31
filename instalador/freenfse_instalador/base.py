"""Fluxo comum da instalação (Compose e nativa): `.env`, arquivos, TLS, saúde e resumo."""

import os
import stat
import time
from pathlib import Path

from freenfse_instalador import saude, segredos


class Instalacao:
    """Passos em ordem; cada modo implementa os seus.

    Nada que seja segredo é impresso: tudo o que o instalador diz passa por `dizer`, que mascara
    qualquer valor secreto conhecido, e os comandos recebem segredos por ambiente/entrada padrão.
    """

    def __init__(
        self, parametros, executor, *, saida=print, dormir=time.sleep, consultar_saude=None
    ):
        """`consultar_saude`: função sem argumentos -> `(codigo_http, corpo)` (troca nos testes)."""
        self.p = parametros
        self.executor = executor
        self._saida = saida
        self._dormir = dormir
        self._consultar_saude = consultar_saude
        self.segredos = {}
        self.gerados = []
        self.avisos = []
        self.arquivos_gravados = []

    # -- saída e arquivos ------------------------------------------------------------------

    def dizer(self, texto=""):
        """Imprime sem nenhum segredo conhecido."""
        self._saida(segredos.mascarar(str(texto), self.segredos.values()))

    def passo(self, texto):
        """Título de uma etapa."""
        self.dizer(f"\n== {texto}")

    def aviso(self, texto):
        """Aviso que também vai para o resumo final."""
        self.avisos.append(texto)
        self.dizer(f"  ! {texto}")

    def gravar(self, caminho, conteudo, *, modo=0o644):
        """Grava um arquivo (ou só descreve, na simulação) com a permissão pedida."""
        caminho = Path(caminho)
        if self.p.simular:
            self.dizer(f"  [simulação] gravaria {caminho} (modo {oct(modo)})")
            return
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(conteudo, encoding="utf-8")
        os.chmod(caminho, modo)
        self.arquivos_gravados.append(caminho)

    def criar_pasta(self, caminho, *, modo=0o755, dono=None):
        """Cria a pasta (idempotente) e, se `dono` for dado (`uid:gid`), tenta ajustar o dono."""
        caminho = Path(caminho)
        if self.p.simular:
            self.dizer(f"  [simulação] criaria a pasta {caminho} (modo {oct(modo)})")
            return
        caminho.mkdir(parents=True, exist_ok=True)
        os.chmod(caminho, modo)
        if dono:
            resultado = self.executor.executar(["chown", dono, str(caminho)], verificar=False)
            if resultado.codigo != 0:
                self.aviso(
                    f"Não consegui ajustar o dono de {caminho} para {dono}. Rode o instalador como "
                    f"root ou execute: chown {dono} {caminho}"
                )

    def executar(self, comando, **opcoes):
        """Roda (ou, na simulação, só descreve) um comando."""
        if self.p.simular:
            self.dizer(f"  [simulação] {' '.join(comando)}")
            return self.executor.executar(comando, **opcoes)
        self.dizer(f"  $ {' '.join(comando)}")
        return self.executor.executar(comando, **opcoes)

    # -- .env ------------------------------------------------------------------------------

    def valores_desejados(self):
        """Valores não secretos do `.env` (o que o instalador define a cada execução)."""
        p = self.p
        valores = {
            "ALLOWED_HOSTS": f"{p.dominio},localhost,127.0.0.1",
            "HTTP_PORT": str(p.porta_http),
            "HTTPS_PORT": str(p.porta_https),
            "LOG_FORMATO": "json",
            "FREENFSE_DADOS": str(p.dados),
            "COOKIES_SEGUROS": "true" if p.https else "false",
            "PROXY_TLS": "true" if p.https else "false",
            "CSRF_TRUSTED_ORIGINS": p.url,
        }
        if p.chave_publica_backup:
            valores["FREENFSE_BACKUP_DESTINATARIO"] = p.chave_publica_backup
        valores.update(self.valores_do_modo())
        return valores

    def valores_do_modo(self):
        """Valores específicos do modo (sobrescrito)."""
        return {}

    def reaproveitar_configuracao(self):
        """Numa nova execução sem `--dados`, mantém a pasta de dados e o backup já configurados."""
        existente = segredos.ler_env(self.p.env)
        if not self.p.extras.get("dados_explicito") and existente.get("FREENFSE_DADOS"):
            self.p.dados = Path(existente["FREENFSE_DADOS"])
        if not self.p.chave_publica_backup and existente.get("FREENFSE_BACKUP_DESTINATARIO"):
            self.p.chave_publica_backup = existente["FREENFSE_BACKUP_DESTINATARIO"]

    def preparar_env(self):
        """Cria/atualiza o `.env` preservando todo segredo que já existe."""
        p = self.p
        existente = segredos.ler_env(p.env)
        valores, gerados = segredos.montar_valores(existente, self.valores_desejados())
        self.gerados = gerados
        self.segredos = {nome: valores[nome] for nome in segredos.SEGREDOS if valores.get(nome)}
        reaproveitados = [n for n in segredos.SEGREDOS if existente.get(n)]
        if p.simular:
            self.dizer(f"  [simulação] gravaria {p.env} (modo 0o600) com {len(valores)} chaves")
        else:
            segredos.escrever_env(p.env, valores, modelo=p.repositorio / ".env.example")
        if reaproveitados:
            self.dizer(
                f"  Segredos já existentes mantidos (não são trocados): {', '.join(reaproveitados)}"
            )
        if gerados:
            self.dizer(f"  Segredos novos gerados e gravados em {p.env}: {', '.join(gerados)}")
        return valores

    # -- backup ----------------------------------------------------------------------------

    def preparar_chave_de_backup(self):
        """Gera o par age (se pedido) e grava só a chave pública no `.env`."""
        p = self.p
        if not p.gerar_chave_backup:
            return
        arquivo = Path(p.gerar_chave_backup)
        if arquivo.exists() or segredos.ler_env(p.env).get("FREENFSE_BACKUP_DESTINATARIO"):
            self.dizer("  Chave de backup já existe: nada foi gerado de novo.")
            return
        resultado = self.executar(["age-keygen", "-o", str(arquivo)])
        publica = self.executar(["age-keygen", "-y", str(arquivo)]).saida.strip()
        if not p.simular:
            os.chmod(arquivo, 0o600)
        p.chave_publica_backup = publica or "age1" + "0" * 58
        self.aviso(
            f"A chave PRIVADA do backup foi gravada em {arquivo}. Copie-a AGORA para fora do "
            "servidor (cofre de senhas, outro computador) e apague este arquivo: sem ela os "
            "backups não podem ser restaurados e, com ela aqui, perdem o sentido."
        )
        return resultado

    # -- pós-instalação ----------------------------------------------------------------------

    def comando_manage(self, *args, ambiente=None):
        """Comando para rodar `manage.py` no ambiente do modo (sobrescrito)."""
        raise NotImplementedError

    def criar_master(self):
        """Cria o primeiro Master com senha aleatória, gravada em arquivo 0600 (nunca impressa)."""
        p = self.p
        if not p.email_master:
            return
        arquivo = Path(p.dados) / "master.senha"
        if arquivo.exists():
            self.dizer(f"  Master já criado antes (senha em {arquivo}).")
            return
        senha = segredos.gerar_senha(20)
        self.segredos["MASTER"] = senha
        self.gravar(arquivo, senha + "\n", modo=0o600)  # antes de criar: a senha não se perde
        comando, env = self.comando_manage(
            "createsuperuser", "--noinput", "--email", p.email_master, "--nome", "Administrador",
            ambiente={"DJANGO_SUPERUSER_PASSWORD": senha},
        )  # fmt: skip
        resultado = self.executar(comando, env=env, verificar=False)
        if resultado.codigo != 0:
            if not p.simular:
                arquivo.unlink(missing_ok=True)
            self.aviso(
                "Não consegui criar o Master (talvez o e-mail já exista). Crie manualmente com "
                "`manage.py createsuperuser`."
            )
            return
        self.aviso(
            f"Senha inicial do Master gravada em {arquivo} (modo 600). Entre, troque a senha, "
            "ative o 2FA e apague o arquivo."
        )

    def criar_usuario_bi(self):
        """Cria o usuário de banco somente leitura para BI (senha só por ambiente/arquivo)."""
        if not self.p.criar_usuario_bi:
            return
        senha = self.segredos.get("FREENFSE_BI_SENHA", "")
        comando, env = self.comando_manage(
            "criar_usuario_bi", ambiente={"FREENFSE_BI_SENHA": senha}
        )
        self.executar(comando, env=env)
        self.dizer("  Usuário de BI criado (senha em FREENFSE_BI_SENHA, no .env).")

    # -- verificação ---------------------------------------------------------------------------

    def verificar_saude(self):
        """Espera o sistema ficar saudável e confere a cifragem dos dados."""
        p = self.p
        if p.simular:
            self.dizer("  [simulação] esperaria /api/saude/ responder ok ou degradado")
            return {}
        consultar = self._consultar_saude or (
            lambda: saude.consultar(
                "127.0.0.1",
                p.porta_https if p.https else p.porta_http,
                p.dominio,
                https=p.https,
            )
        )
        corpo = saude.aguardar(consultar, espera_total=p.espera_da_saude, dormir=self._dormir)
        comando, env = self.comando_manage("verificar_cifragem")
        self.executar(comando, env=env)
        return corpo

    def resumo(self, corpo_da_saude):
        """O que ficou pronto e o que ainda depende de você (sem nenhum segredo)."""
        p = self.p
        self.passo("Pronto")
        self.dizer(f"  Endereço: {p.url}")
        self.dizer(f"  Configuração: {p.env} (permissão 600)")
        self.dizer(f"  Dados e backups: {p.dados}")
        estado = (corpo_da_saude or {}).get("status", "não verificado")
        self.dizer(f"  Estado de saúde: {estado}")
        self.dizer(
            "  GUARDE FORA DO SERVIDOR: a FREENFSE_CHAVES (no .env) e a chave PRIVADA do backup. "
            "Perder a primeira = perder certificados, credenciais e XMLs; perder a segunda = "
            "não conseguir restaurar backups."
        )
        if not (
            p.chave_publica_backup or segredos.ler_env(p.env).get("FREENFSE_BACKUP_DESTINATARIO")
        ):
            self.aviso("Backup NÃO configurado (sem chave pública). Veja docs/instalacao.md.")
        for aviso in self.avisos:
            self.dizer(f"  ! {aviso}")

    # -- fluxo ---------------------------------------------------------------------------------

    def instalar(self):
        """Roda a instalação inteira e devolve o corpo da última leitura de saúde."""
        raise NotImplementedError


def permissao(caminho):
    """Permissões de um arquivo como 'rw-------' (para os testes e o resumo)."""
    return stat.filemode(Path(caminho).stat().st_mode)
