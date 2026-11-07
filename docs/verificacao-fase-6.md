# Verificação da Fase 6 (operação e entrega)

Os testes automatizados cobrem o código com as ferramentas de verdade (`pg_dump`, `pg_restore`, `age`, `nginx`) e um
PostgreSQL real, mas **não há como provar, em desenvolvimento, uma instalação numa VPS limpa nem o Docker/systemd reais**.
Esse é o **roteiro para o usuário** (parte 1 abaixo): instalação limpa numa VPS de teste e restauração de backup.

> **Cuidado:** use uma VPS **descartável**, a **produção restrita** e dados fictícios. Nunca cole `.env`, chaves, o `.pfx`,
> senhas ou XMLs reais em issues, PRs, mensagens ou logs. Destrua a VPS no fim.

## Parte 1 — Roteiro manual numa VPS de teste

### 0. Preparação
1. VPS Linux (Ubuntu 24.04, 2 vCPU, 4 GB) com um **domínio de teste** apontando para o IP dela. Portas 80 e 443 abertas.
2. Instale Docker e o plugin Compose ([docs.docker.com/engine/install](https://docs.docker.com/engine/install/)), `git` e `age`
   (`sudo apt install git age`), e baixe o repositório na branch da fase.
3. **No seu computador**, gere o par de chaves do backup: `age-keygen -o backup.key`. Guarde `backup.key` fora da VPS e anote
   a chave **pública** (a linha `Public key: age1…`).

### 1. Instalar (esperado: termina em "Pronto")
1. Veja o plano sem executar nada: `python3 instalador/instalar.py compose --dominio SEU.DOMINIO --tls letsencrypt --email VOCE@x.com --simular`.
2. Instale: `sudo python3 instalador/instalar.py compose --dominio SEU.DOMINIO --tls letsencrypt --email VOCE@x.com --chave-publica-backup age1… --email-master VOCE@x.com --usuario-bi`.
3. **Esperado:** nenhuma senha, chave ou segredo aparece na tela; o final mostra o endereço `https://SEU.DOMINIO`, o estado
   de saúde e os avisos (guardar `FREENFSE_CHAVES`, apagar `master.senha`).
4. `ls -l .env` → permissão `-rw-------`. `curl -s https://SEU.DOMINIO/api/saude/` → `status` `ok` ou `degradado`
   (`backup: sem_backup` até o primeiro backup é normal).
5. No navegador: cadeado válido, o `http://` redireciona para `https://`; nas ferramentas do navegador, os cookies de sessão
   estão marcados **Secure** e **HttpOnly**.

### 2. Rodar o instalador de novo (idempotência)
1. Antes: `grep '^SECRET_KEY=' .env | sha256sum` e o mesmo para `FREENFSE_CHAVES`. Rode o instalador outra vez (os mesmos
   parâmetros). **Esperado:** os dois hashes iguais, "Segredos já existentes mantidos", nenhum volume ou backup apagado, o sistema
   continua no ar.

### 3. Erros em linguagem simples
1. `docker compose stop backend`. Abra `https://SEU.DOMINIO/accounts/google/login/` → página "O sistema está indisponível…";
   `curl -s https://SEU.DOMINIO/api/versao/` → JSON `{"codigo":"indisponivel",…}` com HTTP 503. `docker compose start backend`.

### 4. Primeiro acesso
1. Entre como Master com a senha de `<dados>/master.senha`, configure o 2FA, troque a senha e **apague o arquivo**.

### 5. Dados cifrados em repouso
1. Faça o roteiro de emissão da Fase 3 (empresa de teste, certificado de teste, uma nota autorizada em produção restrita).
2. Leia a coluna **bruta**: `docker compose exec postgres psql -U freenfse -d freenfse -c "select left(encode(xml_nfse,'escape'),12) from empresa_<CNPJ>.fiscal_nfse where xml_nfse is not null limit 1"`
   → **começa com `v1:`** (nunca `<?xml`). `docker compose exec backend python manage.py verificar_cifragem` → "Todos os … valores
   conferidos estão cifrados."
3. Baixe o XML e o DANFSe pela tela: continuam abrindo normalmente.

### 6. Backup e restauração
1. `docker compose exec backend python manage.py fazer_backup` → "Backup feito". Em `<dados>/backups` há o `.dump.age` e o `.json`.
   `/api/saude/` passa a mostrar `backup: ok`.
2. **Copie** o `.dump.age` e o `.json` para fora da VPS (`scp`), como faria na rotina real.
3. Restaure num banco novo, com a chave privada (siga [`docs/chaves-e-backup.md`](chaves-e-backup.md), "Restaurar"):
   **Esperado:** "Restauração verificada no banco 'freenfse_restaurado'".
4. **Falhas esperadas** (cada uma deve recusar, com mensagem clara): (a) outra chave privada; (b) arquivo `.dump.age` alterado
   (um byte); (c) rodar com outra `FREENFSE_CHAVES` (`-e FREENFSE_CHAVES=1:<outra>`); (d) apagar o `.json`; (e) `--destino` de um
   banco que já existe.
5. (Opcional) Troque os nomes dos bancos como no manual, suba o sistema e confira que as notas continuam lá.

### 7. Alertas, BI e renovação
1. **Alertas:** configure `ALERTAS_SMTP_*` e `ALERTAS_EMAIL_PARA` no `.env` (caixa dedicada), `docker compose up -d`. Provoque a
   falha: troque `FREENFSE_BACKUP_DESTINATARIO` por um valor inválido e rode `fazer_backup` → o comando recusa e, pela tarefa
   agendada (`docker compose exec backend celery -A config call operacao.tasks.fazer_backup`), chega o e-mail "O backup do banco
   falhou". Restaure o valor certo.
2. **BI:** com a senha de `FREENFSE_BI_SENHA` (no `.env`), `psql -h 127.0.0.1 -U freenfse_bi -d freenfse -c 'select count(*) from bi.notas'`
   funciona; `select * from core_usuario` e `create table x(a int)` são **recusados**. Veja [`docs/bi.md`](bi.md).
3. **Renovação do certificado:** `docker run --rm -v <dados>/letsencrypt:/etc/letsencrypt -v <dados>/certbot-www:/var/www/certbot certbot/certbot renew --dry-run`
   → "Congratulations, all simulated renewals succeeded".
4. **Reinício:** `sudo reboot`. Em até 3 minutos `/api/saude/` volta a `ok` sem intervenção (`restart: unless-stopped`; o
   `agendador` pode levar ~2 minutos para voltar a `ok`).

### 8. Registre e destrua
Anote o que divergiu (mensagens, tempos, qualquer segredo que apareceu na tela — **isso seria um defeito grave**) e **destrua a VPS**.

## Parte 2 — Instalação nativa (opcional)

Mesma ideia, com `python3 instalador/instalar.py nativo …` numa VPS com Python 3.10+ para o instalador e 3.14 para o sistema
(`--python`), PostgreSQL 18, Redis, Nginx, git, age e Node. Confira: `systemctl status freenfse-web freenfse-worker freenfse-beat`, `journalctl -u freenfse-web -n 20` (logs em JSON),
`freenfse-manage verificar_cifragem` e o mesmo roteiro das partes 1.4 a 1.7. **Este caminho tem menos cobertura automatizada**
(o instalador é testado com executor simulado e `nginx -t` real, mas systemd e PostgreSQL nativos só se provam aqui).

## Verificação automatizada

```bash
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && pytest
cd ../instalador && python -m pytest          # precisa de pytest; usa o nginx real se existir
cd ../frontend && npm run lint && npm test && npm run build
```

Os testes de backup precisam de `pg_dump`/`pg_restore` (mesma série ou mais nova que o servidor) e `age` no PATH; **sem eles
os testes falham** (não são pulados em silêncio). O CI instala as duas ferramentas.

### Cobertura por critério de aceite

| Critério | Onde | Testes | O que prova |
|---|---|---|---|
| Instalador (item 1) | `instalador/tests/test_segredos.py`, `test_parametros.py`, `test_instalacao.py` | 65 | `.env` com segredos aleatórios e permissão 600; segredo existente nunca trocado; **nenhum segredo na saída nem na linha de comando**; idempotência; HTTPS (Let's Encrypt e próprio) ligando cookies seguros/proxy TLS; Compose e nativo (unidades systemd endurecidas, ordem dos comandos, `nginx -t` real); `--simular` não grava nada; verificação final de saúde |
| **Restauração de backup comprovada** (item 2) | `operacao/tests/test_backup.py` | 25 | backup → banco novo → dados conferidos (linhas por tabela, XML cifrado legível, comentário "verificada"); recusa chave errada, arquivo adulterado, sem manifesto, banco existente, `FREENFSE_CHAVES` errada, divergência com o manifesto; arquivo `age` sem nada em claro; retenção |
| **Coluna de XML cifrada, lida em bruto** (item 3) | `fiscal/tests/test_xml_cifrado.py`, `test_migracao_xml_cifrado.py`, `documentos/tests/test_{exportacao,drive_envio,email_envio}.py` | 11 + 4 + 3 | todas as 7 colunas começam com `v1:` e não deixam XML/chave/CPF à mostra; hash segue sendo o do XML em claro; download, DANFSe, lote, Drive e e-mail partem da coluna cifrada; valor adulterado/trocado é barrado; rotação de chave; migração dos dados existentes (idempotente, reversível, falha sem chaves) |
| **Expurgo de 5 anos com relógio controlado** (item 4) | `documentos/tests/test_retencao.py` | 6 | só o que passou de 5 anos sai; borda exata; 29/02; **com o relógio 10 anos à frente, nenhuma nota, XML, evidência, evento ou auditoria é apagado** |
| Observabilidade (item 5) | `operacao/tests/test_logs.py`, `test_saude.py`, `test_alertas.py`, `documentos/tests/test_alertas_operacionais.py` | 22 + 27 + 11 + 10 | logs JSON de uma linha, com segredos/CPF/e-mail mascarados (formatador, filtro e `LOGGING` real); `/api/saude/` (200/503, sem dados sensíveis, memo); batimento e sonda do beat; alertas por empresa e da plataforma, sem duplicar |
| Views para BI (item 6) | `operacao/tests/test_bi.py` | 18 | consolidação com `empresa_id`; usuário somente leitura (escrita, `public`, tabelas das empresas recusados); sem XML/credenciais; CPF mascarado; retenções; eventos; empresa nova entra sozinha; senha por SCRAM |
| Páginas de erro do Nginx | `nginx -t` e curl contra Nginx real (verificado na entrega); CI do Compose | — | JSON `{codigo, detalhe}` em `/api/`, HTML em `/accounts/`, 413 tratado, páginas internas |

O job do Docker Compose do CI também confere `/api/saude/` pelo Nginx, `verificar_cifragem` e a página de erro com o backend
parado.

## Mutações (alterar o código de propósito para o teste falhar)

Cada mutação troca um trecho de produção, roda os testes do item e restaura o arquivo; o esperado é o teste **falhar**.
**76 mutações: 75 detectadas e 1 equivalente (S9, sem efeito observável).** Duas **sobreviveram na primeira rodada** (B11 e N16) e
viraram testes. Honestidade sobre o processo: a primeira rodada do instalador foi **invalidada** — o `.pyc` da mutação anterior
foi reaproveitado (arquivo mutado e restaurado com o mesmo tamanho e no mesmo segundo) e todas "falhavam" no mesmo teste; o
runner passou a rodar sem gravar *bytecode*, e o lote foi refeito. Depois de cada lote, o `git status` voltou a ficar limpo
(salvo o arquivo que a mutação N9 gerou na raiz, já removido e ignorado no `.gitignore`).

#### Backup e restauração

| # | Mutação | Teste que a detectou |
|---|---|---|
| B1 | backup sem cifrar (grava o dump em claro) | `test_o_backup_e_um_arquivo_age_que_nao_deixa_nada_em_claro` |
| B2 | destinatário não validado (aceita chave privada) | `test_destinatario_ausente_ou_invalido_e_recusado_sem_ecoar_o_valor[destinatarios1-Nunca informe a chave privada]` |
| B3 | restauração sem conferir a contagem de linhas | `test_restaurar_o_backup_num_banco_novo_confere_e_os_dados_batem` |
| B4 | restauração sem abrir os campos cifrados | `test_restaurar_o_backup_num_banco_novo_confere_e_os_dados_batem` |
| B5 | restauração sem conferir o SHA-256 do arquivo | `test_arquivo_adulterado_e_barrado_antes_de_criar_qualquer_banco` |
| B6 | restauração sobrescreve banco existente | `test_restaurar_recusa_um_banco_que_ja_existe` |
| B7 | retenção apaga também o backup mais recente | `test_a_retencao_nunca_apaga_o_unico_backup_mesmo_vencido` |
| B8 | retenção apaga o que ainda está no prazo | `test_a_retencao_apaga_so_os_mais_velhos_que_o_prazo_e_guarda_o_ultimo` |
| B9 | falha do age ignorada | `test_falha_da_cifragem_com_age_nao_vira_backup_bom` |
| B10 | erro de ferramenta externa vaza a senha | `test_o_erro_de_uma_ferramenta_externa_nao_vaza_a_senha_do_banco` |
| B11 | retenção roda mesmo se o backup falhar (antes do dump) | `test_backup_que_falha_nao_aplica_a_retencao_nem_apaga_backups_antigos` (**sobreviveu na 1ª rodada; teste criado**) |
| B12 | restauração falha de abertura deixa o banco vazio | `test_identidade_errada_nao_restaura_nada_e_libera_o_nome` |

#### Criptografia em repouso do XML

| # | Mutação | Teste que a detectou |
|---|---|---|
| X1 | XML da NFS-e e da DPS gravados em claro | `test_o_xml_da_nfse_e_da_dps_ficam_cifrados_na_coluna_bruta` |
| X2 | XML do evento gravado em claro | `test_todas_as_colunas_de_xml_estao_cifradas_depois_de_emitir_e_cancelar` |
| X3 | evidência bruta gravada em claro | `test_todas_as_colunas_de_xml_estao_cifradas_depois_de_emitir_e_cancelar` |
| X4 | documento fiscal da biblioteca gravado em claro | `test_todas_as_colunas_de_xml_estao_cifradas_depois_de_emitir_e_cancelar` |
| X5 | download do XML sem conferir o hash | `test_xml_trocado_por_outro_cifrado_valido_e_barrado_pelo_hash` |
| X6 | migração cifra duas vezes (não idempotente) | `test_rodar_a_conversao_de_novo_nao_cifra_duas_vezes` |
| X7 | verificar_cifragem não enxerga valor em claro | `test_verificar_cifragem_acusa_xml_em_claro_sem_mostrar_o_conteudo` |
| X8 | migração falha em silêncio sem chaves | `test_os_xmls_em_claro_viram_tokens_sem_perder_o_conteudo` |

#### Retenção (expurgo)

| # | Mutação | Teste que a detectou |
|---|---|---|
| R1 | expurgo apaga eventos fiscais | `test_dez_anos_depois_nenhum_documento_fiscal_foi_apagado` |
| R2 | expurgo apaga o XML da nota | `test_dez_anos_depois_nenhum_documento_fiscal_foi_apagado` |
| R3 | retenção de 4 anos em vez de 5 | `test_so_o_que_passou_de_5_anos_e_apagado` |
| R4 | apaga também o que tem exatamente 5 anos | `test_so_o_que_passou_de_5_anos_e_apagado` |
| R5 | tarefa pula empresas inativas | `test_a_tarefa_percorre_todas_as_empresas_inclusive_as_inativas` |
| R6 | retenção configurável aceita zero ano | `test_os_anos_de_retencao_sao_configuraveis_e_nunca_zero` |

#### Logs sem segredos

| # | Mutação | Teste que a detectou |
|---|---|---|
| L1 | log JSON sem máscara na mensagem | `test_os_valores_reais_dos_segredos_da_instalacao_sao_mascarados[erro com chave-somente-para-teste-local]` |
| L2 | filtro de segredos não mascara | `test_o_filtro_mascara_para_qualquer_formatador` |
| L3 | LOGGING sem o filtro de segredos | `test_a_configuracao_da_aplicacao_liga_o_json_e_o_filtro_de_segredos` |
| L4 | CPF não é mascarado no log | `test_cpf_e_email_nao_vao_para_o_log` |
| L5 | exceção sem máscara no log | `test_a_excecao_tambem_e_mascarada` |
| L6 | valores reais dos segredos não são mascarados | `test_os_valores_reais_dos_segredos_da_instalacao_sao_mascarados[erro com chave-somente-para-teste-local]` |
| L7 | e-mail não é mascarado no log | `test_cpf_e_email_nao_vao_para_o_log` |

#### Saúde e agendador

| # | Mutação | Teste que a detectou |
|---|---|---|
| S1 | banco/Redis fora respondem 200 | `test_banco_ou_redis_fora_responde_503_falha[verificar_banco]` |
| S2 | worker fora não degrada o estado | `test_worker_agendador_ou_backup_com_problema_so_degradam[verificar_worker-falha]` |
| S3 | batimento velho conta como bom | `test_batimento_recente_e_ok_e_velho_ou_ausente_e_atrasado` |
| S4 | backup atrasado conta como bom | `test_backup_recente_ok_e_de_ontem_atrasado` |
| S5 | /api/saude/ exige empresa | `test_tudo_certo_responde_200_ok_sem_exigir_login_nem_empresa` |
| S6 | sonda do beat aceita batimento velho | `test_a_sonda_do_beat_falha_sem_batimento_ou_com_batimento_velho` |
| S7 | memo da saúde nunca expira | `test_o_memo_expira` |
| S8 | endpoint de saúde sem memo | `test_o_endpoint_publico_reaproveita_a_resposta_por_alguns_segundos` |
| S9 | memo ignora a configuração (sempre guarda) | _mutante equivalente: sem efeito observável (com validade 0 nada é guardado e a comparação interna também dá falso)_ |

#### Alertas por e-mail

| # | Mutação | Teste que a detectou |
|---|---|---|
| A1 | alerta de emissão repetido a cada rodada | `test_o_mesmo_problema_nao_vira_varios_emails` |
| A2 | alerta de emissão antes do limite de horas | `test_nota_recente_autorizada_ou_rascunho_nao_alerta` |
| A3 | resumo de falhas conta os próprios alertas | `test_so_conta_falha_definitiva_recente_e_nao_os_proprios_alertas` |
| A4 | alerta da plataforma sem limite de um por dia | `test_um_alerta_por_problema_por_dia` |
| A5 | backup que falha não gera alerta | `test_a_tarefa_de_backup_que_falha_dispara_o_alerta` |
| A6 | alerta de emissão manda emitir de novo | `test_nota_sem_resposta_da_sefin_ha_mais_de_2_horas_gera_um_alerta[enviando]` |

#### Views para BI

| # | Mutação | Teste que a detectou |
|---|---|---|
| I1 | CPF do tomador sai sem máscara no BI | `test_cpf_sai_mascarado_e_o_nome_da_pessoa_fisica_nao_sai` |
| I2 | nome da pessoa física sai no BI | `test_cpf_sai_mascarado_e_o_nome_da_pessoa_fisica_nao_sai` |
| I3 | coluna com XML nas views | `test_nenhuma_view_traz_xml_credencial_ou_o_conteudo_do_documento` |
| I4 | usuário de BI não é somente leitura | `test_usuario_de_bi_so_le_o_schema_bi_e_nao_escreve` |
| I5 | usuário de BI é superusuário | `test_usuario_de_bi_so_le_o_schema_bi_e_nao_escreve` |
| I6 | usuário de BI enxerga o schema público | `test_usuario_de_bi_so_le_o_schema_bi_e_nao_escreve` |
| I7 | ISS não retido conta como retenção | `test_retencoes_uma_linha_por_nota_e_tipo_so_com_valor` |
| I8 | verificador SCRAM errado (login falha) | `test_as_views_consolidam_as_empresas_com_o_identificador_de_cada_uma` |
| I9 | empresa nova não entra nas views | `test_uma_empresa_nova_entra_nas_views_sozinha` |

#### Instalador

| # | Mutação | Teste que a detectou |
|---|---|---|
| N1 | segredo existente é regerado | `test_segredo_existente_nunca_e_trocado` |
| N2 | .env gravado com permissão aberta | `test_cria_o_env_com_segredos_fortes_e_permissao_600` |
| N3 | instalador imprime os segredos | `test_nenhum_segredo_aparece_na_saida_nem_na_linha_de_comando` |
| N4 | senha vai na linha de comando | `test_nenhum_segredo_aparece_na_saida_nem_na_linha_de_comando` |
| N5 | Let's Encrypt aceita IP ou nome interno | `test_letsencrypt_exige_email_dominio_publico_e_porta_80` |
| N6 | chave privada age aceita como destinatário | `test_so_a_chave_publica_do_backup_e_aceita` |
| N7 | HTTPS sem cookies seguros | `test_compose_com_certificado_proprio_liga_https_e_cookies_seguros` |
| N8 | HTTPS sem PROXY_TLS | `test_compose_com_certificado_proprio_liga_https_e_cookies_seguros` |
| N9 | --simular grava arquivos | `test_modo_simulado_nao_grava_nem_executa_nada` |
| N10 | % não escapado no systemd | `test_nativo_gera_unidades_systemd_endurecidas_e_o_nginx` |
| N11 | nginx -t omitido antes de recarregar | `test_nativo_comandos_na_ordem_certa_e_senha_do_banco_so_como_verificador` |
| N12 | sistema doente conta como saudável | `test_sistema_nao_saudavel_derruba_a_instalacao` |
| N13 | master recriado a cada execução | `test_master_nao_e_recriado_numa_nova_execucao` |
| N14 | pasta de backups aberta a todos | `test_compose_http_gera_env_override_e_sobe_a_pilha` |
| N15 | chave privada do backup vai para o .env | `test_gerar_chave_de_backup_grava_so_a_publica_no_env_e_manda_guardar_a_privada` |
| N16 | dados explícito ignorado numa nova execução | `test_dados_informado_de_novo_vale_mais_que_o_que_ja_estava_no_env` (**sobreviveu na 1ª rodada; teste criado**) |
| N17 | saída transmitida sem máscara de segredos | `test_comando_longo_mostra_a_saida_aos_poucos_e_sem_segredo` |
| N18 | comando longo falho não levanta erro | `test_comando_longo_que_falha_levanta_o_erro_com_o_final_da_saida` |
| N19 | etapa demorada do Compose não é transmitida | `test_as_etapas_demoradas_do_compose_e_do_nativo_sao_transmitidas` |

### Limitações conhecidas

* **Nada foi provado numa VPS real** (parte 1 deste documento fica com o usuário): Docker, systemd, Let's Encrypt, o build da
  imagem com o `pg_dump` 18 e a subida real do Compose só o CI (job do Compose) e o roteiro exercitam.
* O **instantâneo consistente** do backup (`pg_export_snapshot`) é usado, mas não há teste com escrita concorrente durante o
  dump.
* A máscara de logs é heurística (regex) e não substitui o cuidado de não registrar credenciais.
* O alerta de falhas permanentes não chega se o e-mail da própria empresa é o que está quebrado (fica no log e nas telas de envio).
* Os dados cadastrais e os *snapshots* do tomador continuam em claro no banco (decisão do ADR 0008, com mitigações).
