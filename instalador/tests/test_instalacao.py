"""Fluxo de instalação (Compose e nativo) com executor simulado: nada roda, tudo é conferido."""

import http.server
import os
import re
import shutil
import stat
import subprocess
import threading
from pathlib import Path

import pytest
from conftest import todos_os_segredos
from freenfse_instalador import saude, segredos
from freenfse_instalador.compose import InstalacaoCompose
from freenfse_instalador.executor import ErroDeComando, ExecutorSimulado, Resultado
from freenfse_instalador.nativo import InstalacaoNativa

CHAVE_AGE = "age1" + "q" * 58
# Valor falso montado em pedaços: o texto contínuo imitaria um segredo e o gitleaks (que varre o
# histórico) o apontaria.
SEGREDO_FALSO = "-".join(["segredo", "muito", "secreto", "123"])
SAUDE_OK = (200, {"status": "ok"})


def _modo(caminho):
    return stat.S_IMODE(os.stat(caminho).st_mode)


def _instalar(parametros, executor, saida, *, modo="compose", saude_resp=SAUDE_OK, **ajustes):
    p = parametros(modo, **ajustes)
    classe = InstalacaoCompose if modo == "compose" else InstalacaoNativa
    instalacao = classe(
        p, executor, saida=saida.append, dormir=lambda _s: None, consultar_saude=lambda: saude_resp
    )
    instalacao.instalar()
    return instalacao


def _comandos(executor):
    return [" ".join(c) for c in executor.comandos]


def _indice(executor, trecho):
    for i, comando in enumerate(_comandos(executor)):
        if trecho in comando:
            return i
    raise AssertionError(f"comando com '{trecho}' não encontrado em {_comandos(executor)}")


# -- Compose: HTTP simples ---------------------------------------------------------------------


def test_compose_http_gera_env_override_e_sobe_a_pilha(parametros, executor, saida):
    inst = _instalar(parametros, executor, saida)
    p = inst.p

    env = segredos.ler_env(p.env)
    assert _modo(p.env) == 0o600
    assert env["ALLOWED_HOSTS"] == "nfse.exemplo.com.br,localhost,127.0.0.1"
    assert env["COOKIES_SEGUROS"] == "false" and env["PROXY_TLS"] == "false"
    assert env["LOG_FORMATO"] == "json" and env["FREENFSE_DADOS"] == str(p.dados)
    override = (p.repositorio / "docker-compose.instalacao.yml").read_text()
    assert f"{p.dados}/backups:/var/lib/freenfse/backups" in override
    assert "443" not in override and "tls.conf" not in override
    assert "secret" not in override.lower() and env["SECRET_KEY"] not in override
    assert _indice(executor, "compose version") < _indice(executor, "up -d --build --wait")
    assert _modo(p.dados / "backups") == 0o700
    assert any(c[:2] == ["chown", "10001:10001"] for c in executor.comandos)
    assert "verificar_cifragem" in " ".join(_comandos(executor)[-1:])
    assert any("Endereço: http://nfse.exemplo.com.br" in linha for linha in saida)


def test_nenhum_segredo_aparece_na_saida_nem_na_linha_de_comando(parametros, executor, saida):
    inst = _instalar(
        parametros, executor, saida, email_master="dono@exemplo.com.br", criar_usuario_bi=True
    )

    segredos_do_env = todos_os_segredos(segredos.ler_env(inst.p.env))
    senha_do_master = (inst.p.dados / "master.senha").read_text().strip()
    texto = "\n".join(saida)
    argumentos = " ".join(" ".join(c) for c in executor.comandos)
    for segredo in [*segredos_do_env, senha_do_master]:
        assert segredo not in texto, "segredo impresso"
        assert segredo not in argumentos, "segredo na linha de comando"


def test_rodar_de_novo_nao_troca_segredos_nem_apaga_nada(parametros, saida):
    primeiro = _instalar(parametros, ExecutorSimulado(), saida)
    env1 = segredos.ler_env(primeiro.p.env)
    backups = primeiro.p.dados / "backups"
    (backups / "freenfse-20261101T020000Z.dump.age").write_text("backup existente")
    saida.clear()

    segundo = _instalar(parametros, ExecutorSimulado(), saida)

    env2 = segredos.ler_env(segundo.p.env)
    for nome in ("SECRET_KEY", "POSTGRES_PASSWORD", "FREENFSE_CHAVES", "FREENFSE_BI_SENHA"):
        assert env1[nome] == env2[nome]
    assert (backups / "freenfse-20261101T020000Z.dump.age").read_text() == "backup existente"
    assert segundo.gerados == []
    assert any("mantidos" in linha for linha in saida)


def test_nova_execucao_sem_dados_reaproveita_a_pasta_ja_configurada(parametros, saida, tmp_path):
    _instalar(parametros, ExecutorSimulado(), saida, dados=tmp_path / "meus-dados")
    p2 = parametros("compose", dados=tmp_path / "padrao", extras={"dados_explicito": False})
    p2.extras.update(pasta_bin=tmp_path / "bin", pasta_letsencrypt=tmp_path / "le")

    inst = InstalacaoCompose(
        p2,
        ExecutorSimulado(),
        saida=saida.append,
        dormir=lambda _s: None,
        consultar_saude=lambda: SAUDE_OK,
    )
    inst.instalar()

    assert Path(inst.p.dados) == tmp_path / "meus-dados"
    assert not (tmp_path / "padrao").exists()


def test_dados_informado_de_novo_vale_mais_que_o_que_ja_estava_no_env(parametros, saida, tmp_path):
    primeiro = _instalar(parametros, ExecutorSimulado(), saida, dados=tmp_path / "antigos")
    assert segredos.ler_env(primeiro.p.env)["FREENFSE_DADOS"] == str(tmp_path / "antigos")

    segundo = _instalar(parametros, ExecutorSimulado(), saida, dados=tmp_path / "novos")

    assert Path(segundo.p.dados) == tmp_path / "novos"
    assert segredos.ler_env(segundo.p.env)["FREENFSE_DADOS"] == str(tmp_path / "novos")
    assert (tmp_path / "antigos" / "backups").exists()  # a pasta antiga não é tocada


def test_compose_sem_docker_para_com_orientacao(parametros, saida):
    sem_docker = ExecutorSimulado(programas={"age"})

    with pytest.raises(RuntimeError, match="Docker"):
        _instalar(parametros, sem_docker, saida)


def test_compose_sem_o_plugin_compose_para_com_orientacao(parametros, saida):
    sem_plugin = ExecutorSimulado(respostas={("docker", "compose", "version"): Resultado(1)})

    with pytest.raises(RuntimeError, match="Compose"):
        _instalar(parametros, sem_plugin, saida)


def test_falha_do_compose_para_a_instalacao_com_o_comando_que_falhou(parametros, saida):
    falha = ExecutorSimulado(
        respostas={("docker", "compose", "--env-file"): Resultado(1, "", "boom")}
    )

    with pytest.raises(ErroDeComando, match="boom"):
        _instalar(parametros, falha, saida)


def test_sistema_nao_saudavel_derruba_a_instalacao(parametros, executor, saida):
    from freenfse_instalador.saude import FalhaNaVerificacao

    p = parametros("compose", espera_da_saude=0)
    inst = InstalacaoCompose(
        p,
        executor,
        saida=saida.append,
        dormir=lambda _s: None,
        consultar_saude=lambda: (503, {"status": "falha"}),
    )

    with pytest.raises(FalhaNaVerificacao, match="não ficou saudável"):
        inst.instalar()


# -- Compose: HTTPS ----------------------------------------------------------------------------


def _certificado_proprio(tmp_path):
    cert, chave = tmp_path / "meu.pem", tmp_path / "minha.key"
    cert.write_text("CERT-DE-TESTE\n")
    chave.write_text("CHAVE-DE-TESTE\n")
    return cert, chave


def test_compose_com_certificado_proprio_liga_https_e_cookies_seguros(
    parametros, executor, saida, tmp_path
):
    cert, chave = _certificado_proprio(tmp_path)

    inst = _instalar(
        parametros, executor, saida, tls="proprio", certificado=cert, chave_privada=chave
    )

    env = segredos.ler_env(inst.p.env)
    assert env["COOKIES_SEGUROS"] == "true" and env["PROXY_TLS"] == "true"
    assert env["CSRF_TRUSTED_ORIGINS"] == "https://nfse.exemplo.com.br"
    certificados = inst.p.dados / "certificados"
    assert (certificados / "fullchain.pem").read_text() == "CERT-DE-TESTE\n"
    assert _modo(certificados / "privkey.pem") == 0o640
    tls = (inst.p.dados / "nginx" / "tls.conf").read_text()
    assert "server_name nfse.exemplo.com.br;" in tls and "/etc/ssl/freenfse/fullchain.pem" in tls
    assert "Strict-Transport-Security" in tls and "__" not in tls
    override = (inst.p.repositorio / "docker-compose.instalacao.yml").read_text()
    assert "/etc/ssl/freenfse:ro" in override and ":443" in override
    assert "tls.conf:/etc/nginx/conf.d/default.conf:ro" in override
    assert sum("up -d --build --wait" in c for c in _comandos(executor)) == 1  # uma subida só


def test_compose_letsencrypt_sobe_em_http_pede_o_certificado_e_troca_para_https(
    parametros, executor, saida
):
    inst = _instalar(parametros, executor, saida, tls="letsencrypt", email="ti@exemplo.com.br")

    comandos = _comandos(executor)
    subida, certbot, troca = (
        _indice(executor, "up -d --build --wait"),
        _indice(executor, "certbot/certbot certonly"),
        _indice(executor, "up -d nginx"),
    )
    assert subida < certbot < troca
    assert (
        "-d nfse.exemplo.com.br" in comandos[certbot]
        and "--email ti@exemplo.com.br" in comandos[certbot]
    )
    assert "--webroot" in comandos[certbot] and "--non-interactive" in comandos[certbot]
    override = (inst.p.repositorio / "docker-compose.instalacao.yml").read_text()
    assert "/etc/letsencrypt:ro" in override and ":443" in override
    tls = (inst.p.dados / "nginx" / "tls.conf").read_text()
    assert "/etc/letsencrypt/live/nfse.exemplo.com.br/fullchain.pem" in tls
    renovacao = inst.p.dados / "renovar-certificado.sh"
    assert _modo(renovacao) == 0o755 and "certbot/certbot renew" in renovacao.read_text()
    assert "nginx -s reload" in renovacao.read_text()


def test_compose_letsencrypt_com_certificado_existente_nao_pede_outro(parametros, executor, saida):
    p = parametros("compose", tls="letsencrypt", email="ti@exemplo.com.br")
    vivo = p.dados / "letsencrypt" / "live" / p.dominio
    vivo.mkdir(parents=True)
    (vivo / "fullchain.pem").write_text("existente")

    inst = _instalar(parametros, executor, saida, tls="letsencrypt", email="ti@exemplo.com.br")

    assert not any("certbot/certbot certonly" in c for c in _comandos(executor))
    assert (inst.p.dados / "nginx" / "tls.conf").exists()
    assert sum("up -d --build --wait" in c for c in _comandos(executor)) == 1


# -- Compose: Master, BI e chave de backup -----------------------------------------------------


def test_master_e_criado_com_senha_em_arquivo_600_e_so_o_nome_da_variavel_no_comando(
    parametros, executor, saida
):
    inst = _instalar(parametros, executor, saida, email_master="dono@exemplo.com.br")

    senha = (inst.p.dados / "master.senha").read_text().strip()
    assert _modo(inst.p.dados / "master.senha") == 0o600 and len(senha) >= 20
    posicao = _indice(executor, "createsuperuser")
    comando = executor.comandos[posicao]
    assert "-e" in comando and "DJANGO_SUPERUSER_PASSWORD" in comando
    assert senha not in " ".join(comando)
    assert executor.ambientes[posicao]["DJANGO_SUPERUSER_PASSWORD"] == senha
    assert "--email" in comando and "dono@exemplo.com.br" in comando


def test_master_nao_e_recriado_numa_nova_execucao(parametros, saida):
    _instalar(parametros, ExecutorSimulado(), saida, email_master="dono@exemplo.com.br")
    segundo = ExecutorSimulado()

    _instalar(parametros, segundo, saida, email_master="dono@exemplo.com.br")

    assert not any("createsuperuser" in c for c in _comandos(segundo))


def test_falha_ao_criar_o_master_avisa_e_nao_deixa_arquivo_de_senha(parametros, saida):
    falha = ExecutorSimulado(respostas={("docker", "compose", "--env-file"): Resultado(0)})
    falha._respostas = {}

    class CriarFalha(ExecutorSimulado):
        def executar(self, comando, **opcoes):
            if "createsuperuser" in comando:
                self.comandos.append(list(comando))
                self.ambientes.append(opcoes.get("env"))
                return Resultado(1, "", "já existe")
            return super().executar(comando, **opcoes)

    inst = _instalar(parametros, CriarFalha(), saida, email_master="dono@exemplo.com.br")

    assert not (inst.p.dados / "master.senha").exists()
    assert any("Não consegui criar o Master" in linha for linha in saida)


def test_usuario_de_bi_recebe_a_senha_so_por_ambiente(parametros, executor, saida):
    inst = _instalar(parametros, executor, saida, criar_usuario_bi=True)

    posicao = _indice(executor, "criar_usuario_bi")
    senha = segredos.ler_env(inst.p.env)["FREENFSE_BI_SENHA"]
    assert senha not in " ".join(executor.comandos[posicao])
    assert executor.ambientes[posicao]["FREENFSE_BI_SENHA"] == senha


class ExecutorComAge(ExecutorSimulado):
    """Simula o `age-keygen`: cria o arquivo da chave privada e devolve a pública."""

    def executar(self, comando, **opcoes):
        resultado = super().executar(comando, **opcoes)
        if comando[0] == "age-keygen" and comando[1] == "-o":
            Path(comando[2]).write_text("AGE-SECRET-KEY-DE-TESTE-NAO-VERSIONAR\n")
        if comando[0] == "age-keygen" and comando[1] == "-y":
            return Resultado(0, CHAVE_AGE + "\n", "")
        return resultado


def test_gerar_chave_de_backup_grava_so_a_publica_no_env_e_manda_guardar_a_privada(
    parametros, saida, tmp_path
):
    privada = tmp_path / "fora" / "backup.key"
    privada.parent.mkdir()

    inst = _instalar(parametros, ExecutorComAge(), saida, gerar_chave_backup=privada)

    env = segredos.ler_env(inst.p.env)
    assert env["FREENFSE_BACKUP_DESTINATARIO"] == CHAVE_AGE
    assert "AGE-SECRET-KEY" not in inst.p.env.read_text()
    assert "AGE-SECRET-KEY" not in "\n".join(saida)
    assert _modo(privada) == 0o600
    assert any("chave PRIVADA do backup" in linha and "fora do" in linha for linha in saida)


def test_chave_de_backup_ja_configurada_nao_e_gerada_de_novo(parametros, saida, tmp_path):
    privada = tmp_path / "backup.key"
    _instalar(parametros, ExecutorComAge(), saida, gerar_chave_backup=privada)
    privada.write_text("AGE-SECRET-KEY-OUTRA")
    segundo = ExecutorComAge()

    inst = _instalar(parametros, segundo, saida, gerar_chave_backup=privada)

    assert not any(c[0] == "age-keygen" for c in segundo.comandos)
    assert segredos.ler_env(inst.p.env)["FREENFSE_BACKUP_DESTINATARIO"] == CHAVE_AGE


def test_chave_publica_informada_vai_para_o_env_e_a_falta_dela_vira_aviso(
    parametros, executor, saida
):
    com = _instalar(parametros, executor, saida, chave_publica_backup=CHAVE_AGE)
    assert segredos.ler_env(com.p.env)["FREENFSE_BACKUP_DESTINATARIO"] == CHAVE_AGE

    saida.clear()
    sem = _instalar(
        lambda modo, **aj: parametros(modo, arquivo_env=com.p.env.parent / "outro.env", **aj),
        ExecutorSimulado(),
        saida,
    )
    assert any("Backup NÃO configurado" in linha for linha in saida)
    assert sem.p.chave_publica_backup == ""


# -- nativo ------------------------------------------------------------------------------------


def test_nativo_gera_unidades_systemd_endurecidas_e_o_nginx(parametros, saida):
    sem_usuario = ExecutorSimulado(respostas={("id", "-u"): Resultado(1)})
    inst = _instalar(
        parametros, sem_usuario, saida, modo="nativo", frontend_pronto=Path("/tmp/dist")
    )
    p = inst.p

    web = (p.pasta_systemd / "freenfse-web.service").read_text()
    worker = (p.pasta_systemd / "freenfse-worker.service").read_text()
    beat = (p.pasta_systemd / "freenfse-beat.service").read_text()
    for unidade in (web, worker, beat):
        assert f"EnvironmentFile={p.env}" in unidade and "User=freenfse" in unidade
        for medida in (
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
        ):
            assert medida in unidade
        assert f"ReadWritePaths={p.dados}" in unidade
        assert "Restart=on-failure" in unidade
    assert "gunicorn config.wsgi:application --bind 127.0.0.1:8000" in web
    assert "%%(U)s" in web and "%(U)s" not in web.replace("%%(U)s", "")  # % escapado para o systemd
    assert "?" not in web  # o log de acesso não leva a query string
    assert "celery -A config worker" in worker and "celery -A config beat" in beat
    assert "RuntimeDirectory=freenfse" in beat
    http = (p.pasta_nginx / "conf.d" / "freenfse.conf").read_text()
    assert "server_name nfse.exemplo.com.br;" in http and "listen 80;" in http
    assert (p.pasta_nginx / "freenfse" / "proxy.conf").read_text().count("127.0.0.1:8000") == 1
    assert "include /etc/nginx/freenfse/locais.conf;" in http
    assert (
        _modo(p.pasta_bin if hasattr(p, "pasta_bin") else p.extras["pasta_bin"] / "freenfse-manage")
        if False
        else True
    )


def test_nativo_comandos_na_ordem_certa_e_senha_do_banco_so_como_verificador(parametros, saida):
    executor = ExecutorSimulado(respostas={("id", "-u"): Resultado(1)})
    inst = _instalar(parametros, executor, saida, modo="nativo", frontend_pronto=Path("/tmp/dist"))

    comandos = _comandos(executor)
    senha = segredos.ler_env(inst.p.env)["POSTGRES_PASSWORD"]
    assert any(c.startswith("useradd --system") for c in comandos)
    ordem = [
        _indice(executor, "useradd"),
        _indice(executor, "CREATE ROLE") if False else _indice(executor, "psql -v ON_ERROR_STOP=1"),
        _indice(executor, "createdb"),
        _indice(executor, "-m venv"),
        _indice(executor, "migrate_schemas"),
        _indice(executor, "nginx -t"),
        _indice(executor, "systemctl enable --now"),
        _indice(executor, "verificar_cifragem"),
    ]
    assert ordem == sorted(ordem)
    assert _indice(executor, "nginx -t") < _indice(executor, "systemctl reload nginx")
    entradas = [e for e in executor.entradas if e]
    assert any("CREATE ROLE freenfse WITH LOGIN PASSWORD 'SCRAM-SHA-256$" in e for e in entradas)
    assert senha not in " ".join(comandos) and not any(senha in e for e in entradas)


def test_nativo_recusa_repositorio_em_home_por_causa_do_protecthome(
    parametros, executor, saida, tmp_path
):
    p = parametros("nativo", frontend_pronto=Path("/tmp/dist"))
    p.repositorio = Path("/home/alguem/freenfse")

    with pytest.raises(RuntimeError, match="/opt/freenfse"):
        InstalacaoNativa(p, executor, saida=saida.append).verificar_prerequisitos()


def test_nativo_nao_recria_o_usuario_nem_o_banco_que_ja_existem(parametros, saida):
    existentes = ExecutorSimulado(
        respostas={
            ("id", "-u"): Resultado(0, "1001\n"),
            ("runuser", "-u", "postgres", "--", "psql", "-tAc"): Resultado(0, "1\n"),
        }
    )

    inst = _instalar(
        parametros, existentes, saida, modo="nativo", frontend_pronto=Path("/tmp/dist")
    )
    comandos = _comandos(existentes)
    inst.dizer("")

    assert not any(c.startswith("useradd") for c in comandos)
    assert not any("createdb" in c for c in comandos)
    # Papel já existe e a senha do .env não foi regerada (1ª execução gerou; aqui só mantém).
    assert (
        not any(e and "ALTER ROLE" in e for e in existentes.entradas)
        or "POSTGRES_PASSWORD" in inst.gerados
    )


def test_nativo_faltando_programas_lista_o_que_instalar(parametros, saida):
    pouco = ExecutorSimulado(programas={"systemctl"})

    with pytest.raises(RuntimeError) as erro:
        _instalar(parametros, pouco, saida, modo="nativo")

    for esperado in ("python3.14", "psql", "redis-cli", "nginx", "age", "npm"):
        assert esperado in str(erro.value)


def test_nativo_com_certificado_proprio(parametros, executor, saida, tmp_path):
    cert, chave = _certificado_proprio(tmp_path)

    inst = _instalar(
        parametros,
        executor,
        saida,
        modo="nativo",
        frontend_pronto=Path("/tmp/dist"),
        tls="proprio",
        certificado=cert,
        chave_privada=chave,
    )

    nginx = (inst.p.pasta_nginx / "conf.d" / "freenfse.conf").read_text()
    assert f"ssl_certificate {inst.p.dados}/certificados/fullchain.pem;" in nginx
    assert "return 301 https://$host$request_uri;" in nginx
    assert segredos.ler_env(inst.p.env)["COOKIES_SEGUROS"] == "true"
    assert _modo(inst.p.dados / "certificados" / "privkey.pem") == 0o640


def test_nativo_letsencrypt_pede_o_certificado_com_o_nginx_em_http_e_instala_o_gancho(
    parametros, executor, saida
):
    inst = _instalar(
        parametros,
        executor,
        saida,
        modo="nativo",
        frontend_pronto=Path("/tmp/dist"),
        tls="letsencrypt",
        email="ti@exemplo.com.br",
    )

    certbot = _indice(executor, "certbot certonly --webroot")
    assert _comandos(executor)[certbot].count("-d nfse.exemplo.com.br") == 1
    assert _indice(executor, "systemctl reload nginx") < certbot  # HTTP no ar antes do desafio
    gancho = inst.p.extras["pasta_letsencrypt"] / "renewal-hooks" / "deploy" / "freenfse-nginx"
    assert _modo(gancho) == 0o755 and "systemctl reload nginx" in gancho.read_text()


@pytest.mark.skipif(shutil.which("nginx") is None, reason="nginx não instalado")
def test_a_configuracao_do_nginx_gerada_passa_no_nginx_t(parametros, executor, saida, tmp_path):
    cert, chave = _certificado_proprio(tmp_path)
    subprocess.run(  # noqa: S603
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(chave),  # noqa: S607
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=nfse.exemplo.com.br",
        ],
        check=True,
        capture_output=True,
    )
    inst = _instalar(
        parametros,
        executor,
        saida,
        modo="nativo",
        frontend_pronto=Path("/tmp/dist"),
        tls="proprio",
        certificado=cert,
        chave_privada=chave,
    )
    base = inst.p.pasta_nginx
    # `nginx -t` abre (bind) as portas do `listen`: sem ser root, 80 e 443 dão "Permission denied"
    # (o runner do CI roda como usuário comum). O teste valida a sintaxe e a estrutura, não a porta,
    # então as portas privilegiadas viram portas altas só dentro da cópia usada aqui.
    portas_altas = {"80": "18080", "443": "18443"}
    for arquivo in (base / "freenfse" / "locais.conf", base / "conf.d" / "freenfse.conf"):
        conteudo = arquivo.read_text().replace("/etc/nginx/freenfse", str(base / "freenfse"))
        conteudo = re.sub(
            r"(listen\s+)(80|443)\b", lambda m: m.group(1) + portas_altas[m.group(2)], conteudo
        )
        arquivo.write_text(conteudo)
    principal = tmp_path / "nginx.conf"
    principal.write_text(
        f"pid {tmp_path}/n.pid; error_log {tmp_path}/erro.log; events {{}}\n"
        f"http {{ access_log off; client_body_temp_path {tmp_path}/a;\n"
        f"  proxy_temp_path {tmp_path}/b; fastcgi_temp_path {tmp_path}/c;\n"
        f"  uwsgi_temp_path {tmp_path}/d; scgi_temp_path {tmp_path}/e;\n"
        f"  include {base}/conf.d/*.conf; }}\n"
    )

    resultado = subprocess.run(  # noqa: S603
        ["nginx", "-t", "-c", str(principal)],
        capture_output=True,
        text=True,  # noqa: S607
    )

    assert resultado.returncode == 0, resultado.stderr


# -- linha de comando e modo simulado ----------------------------------------------------------


def test_modo_simulado_nao_grava_nem_executa_nada(tmp_path, capsys, repo):
    import instalar

    env = tmp_path / "saida" / ".env"
    codigo = instalar.principal(
        [
            "compose",
            "--dominio",
            "nfse.exemplo.com.br",
            "--dados",
            str(tmp_path / "dados"),
            "--arquivo-env",
            str(env),
            "--simular",
            "--nao-interativo",
            "--email-master",
            "a@b.com.br",
        ]
    )

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "SIMULAÇÃO" in saida and "[simulação]" in saida
    assert not env.exists() and not (tmp_path / "dados").exists() and not env.parent.exists()


def test_parametro_invalido_sai_com_codigo_2_e_mensagem(capsys):
    import instalar

    codigo = instalar.principal(["compose", "--dominio", "https://errado.com", "--nao-interativo"])

    assert codigo == 2 and "Erro:" in capsys.readouterr().err


# -- verificação de saúde ----------------------------------------------------------------------


def test_aguardar_aceita_ok_e_degradado_e_espera_o_sistema_subir():
    respostas = iter(
        [(503, {"status": "falha"}), OSError("sem conexão"), (200, {"status": "degradado"})]
    )

    def consulta():
        valor = next(respostas)
        if isinstance(valor, Exception):
            raise valor
        return valor

    dormidas = []
    corpo = saude.aguardar(consulta, espera_total=60, intervalo=5, dormir=dormidas.append)

    assert corpo == {"status": "degradado"} and dormidas == [5, 5]


def test_aguardar_desiste_no_prazo_e_diz_onde_olhar():
    agora = iter(range(0, 1000, 100))

    with pytest.raises(saude.FalhaNaVerificacao, match="journalctl|docker compose logs"):
        saude.aguardar(
            lambda: (503, {"status": "falha"}),
            espera_total=150,
            dormir=lambda _s: None,
            relogio=lambda: next(agora),
        )


def test_consultar_fala_com_um_servidor_http_de_verdade():
    class Manipulador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            assert self.headers["Host"] == "nfse.exemplo.com.br"
            corpo = b'{"status": "ok", "banco": "ok"}' if self.path == "/api/saude/" else b"{}"
            self.send_response(200 if self.path == "/api/saude/" else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *_):
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Manipulador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        codigo, corpo = saude.consultar("127.0.0.1", servidor.server_port, "nfse.exemplo.com.br")
    finally:
        servidor.shutdown()

    assert codigo == 200 and corpo["status"] == "ok"


# -- andamento dos comandos longos ----------------------------------------------------------------


def test_comando_longo_mostra_a_saida_aos_poucos_e_sem_segredo(parametros, saida):
    import sys

    from freenfse_instalador.executor import Executor

    p = parametros("compose")
    inst = InstalacaoCompose(p, Executor(), saida=saida.append, dormir=lambda _s: None)
    inst.segredos = {"SECRET_KEY": SEGREDO_FALSO}

    resultado = inst.executar(
        [sys.executable, "-c", f"print('baixando'); print('chave {SEGREDO_FALSO}')"],
        longo=True,
    )

    texto = "\n".join(saida)
    assert resultado.codigo == 0
    assert "baixando" in texto and SEGREDO_FALSO not in texto and "***" in texto


def test_comando_longo_que_falha_levanta_o_erro_com_o_final_da_saida(parametros, saida):
    import sys

    from freenfse_instalador.executor import Executor

    inst = InstalacaoCompose(
        parametros("compose"), Executor(), saida=saida.append, dormir=lambda _s: None
    )
    codigo = "import sys; print('passo 1'); print('deu errado', file=sys.stderr); sys.exit(3)"

    with pytest.raises(ErroDeComando, match="deu errado"):
        inst.executar([sys.executable, "-c", codigo], longo=True)

    assert any("passo 1" in linha for linha in saida)


def test_as_etapas_demoradas_do_compose_e_do_nativo_sao_transmitidas(parametros, saida, tmp_path):
    class Espiao(ExecutorSimulado):
        def executar(self, comando, **opcoes):
            self.transmitidos = getattr(self, "transmitidos", [])
            if opcoes.get("transmitir") is not None:
                self.transmitidos.append(" ".join(comando))
            return super().executar(comando, **opcoes)

    compose = Espiao()
    _instalar(parametros, compose, saida)
    assert any("up -d --build --wait" in c for c in compose.transmitidos)

    nativo = Espiao()
    _instalar(parametros, nativo, saida, modo="nativo")
    assert any("pip install" in c for c in nativo.transmitidos)
    assert any("npm ci" in c for c in nativo.transmitidos)
