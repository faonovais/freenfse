"""HTTPS: configuração do Nginx a partir do modelo, comandos do certbot e renovação."""

from pathlib import Path

RAIZ_ACME = "/var/www/certbot"


def renderizar_nginx_tls(modelo, *, dominio, certificado, chave, raiz, erros):
    """Preenche `docker/nginx/tls.conf.modelo` (mesmo modelo para o Compose e o nativo)."""
    texto = Path(modelo).read_text(encoding="utf-8")
    trocas = {
        "__DOMINIO__": dominio,
        "__CERTIFICADO__": certificado,
        "__CHAVE__": chave,
        "__RAIZ__": raiz,
        "__ERROS__": erros,
    }
    for marca, valor in trocas.items():
        texto = texto.replace(marca, str(valor))
    return texto


def caminhos_letsencrypt(dominio, base="/etc/letsencrypt"):
    """`(certificado, chave)` que o certbot grava para o domínio."""
    return (f"{base}/live/{dominio}/fullchain.pem", f"{base}/live/{dominio}/privkey.pem")


def comando_certbot_docker(*, dominio, email, pasta_letsencrypt, pasta_acme):
    """`certbot certonly --webroot` num contêiner (desafio HTTP-01 pela porta 80)."""
    return [
        "docker", "run", "--rm",
        "-v", f"{pasta_letsencrypt}:/etc/letsencrypt",
        "-v", f"{pasta_acme}:{RAIZ_ACME}",
        "certbot/certbot", "certonly", "--webroot", "-w", RAIZ_ACME,
        "-d", dominio, "--email", email, "--agree-tos", "--no-eff-email",
        "--non-interactive", "--keep-until-expiring",
    ]  # fmt: skip


def comando_certbot_nativo(*, dominio, email, pasta_acme):
    """`certbot certonly --webroot` instalado no servidor."""
    return [
        "certbot", "certonly", "--webroot", "-w", str(pasta_acme),
        "-d", dominio, "--email", email, "--agree-tos", "--no-eff-email",
        "--non-interactive", "--keep-until-expiring",
    ]  # fmt: skip


def script_de_renovacao_docker(*, pasta_letsencrypt, pasta_acme, comando_compose):
    """Script (shell) que renova o certificado e recarrega o Nginx do Compose."""
    compose = " ".join(comando_compose)
    return (
        "#!/bin/sh\n"
        "# Renova o certificado Let's Encrypt e recarrega o Nginx. Gerado pelo instalador.\n"
        "set -eu\n"
        f"docker run --rm -v {pasta_letsencrypt}:/etc/letsencrypt -v {pasta_acme}:{RAIZ_ACME} \\\n"
        f"  certbot/certbot renew --webroot -w {RAIZ_ACME} --quiet\n"
        f"{compose} exec -T nginx nginx -s reload\n"
    )
