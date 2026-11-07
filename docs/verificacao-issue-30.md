# Verificação da issue #30 (instalador com Python 3.10+ e quebras de linha fixas)

Dois defeitos da Fase 6, corrigidos juntos:

1. `instalador/freenfse_instalador/parametros.py` usava `except TypeError, ValueError:`, sintaxe que só existe no **Python 3.14**
   (PEP 758). O instalador roda com o Python do **servidor** (Ubuntu 24.04 tem 3.12), então não chegava a executar.
   **Causa raiz:** o CI aplicava ao instalador a configuração do backend (`backend/ruff.toml`, alvo `py314`), e o `ruff format`
   reescreveu `except (A, B):` para a forma nova. Agora o instalador tem a própria configuração (`instalador/ruff.toml`, alvo
   `py310`, herdando as demais regras do backend).
2. Faltava `.gitattributes`. Um clone no Windows (`core.autocrlf=true`) recebia CRLF, que quebra o `entrypoint` dos
   contêineres (`#!/bin/sh\r`) e os scripts shell.

## O que mudou

* **Versão mínima declarada**: `PYTHON_MINIMO = (3, 10)` em `freenfse_instalador/versao.py`. O `instalar.py` confere a versão
  **antes de importar o resto**; com Python mais antigo imprime uma linha clara e sai com código 2 (nada de `SyntaxError`).
  Uma análise estática de versão mínima (vermin) do instalador deu **3.9**, então o 3.10 tem folga.
* **CI**: novo job `Instalador (Python 3.10 / 3.12 / 3.14)` roda a suíte do instalador em cada versão (pytest fixado igual
  ao do backend). O `ruff` do instalador usa `instalador/ruff.toml`.
* **`.gitattributes`**: `* text=auto` e `eol=lf` para `*.sh`, `entrypoint*`, `Dockerfile*`, `*.dockerfile`, `*.conf` e
  `*.modelo` (Nginx), `*.service`, `*.timer`, `*.socket` (systemd), `*.py` (têm shebang) e `.env*`; binários (`*.woff2`,
  imagens, PDF, zip, xlsx) marcados como `binary`. Os 445 arquivos já versionados já estavam com LF: renormalizar não mudou nenhum.
* **Testes**: `tests/test_versao.py` (regra da versão, mensagem e o `instalar.py` rodando "como um 3.9") e
  `tests/test_quebras_de_linha.py` (nenhum arquivo versionado de tipo sensível com CRLF; `.gitattributes` fixa LF em cada tipo;
  um arquivo com CRLF é normalizado ao entrar num repositório).
* **Manual de instalação**: versão mínima do Python do instalador, a diferença para o Python 3.14 do modo nativo e o aviso
  de clone no Windows.

## Roteiro manual

1. **Python mais antigo.** Num servidor (ou contêiner) com Python 3.9 ou menor, rode `python3 instalador/instalar.py compose
   --simular`. Esperado: uma mensagem dizendo que precisa do Python 3.10 ou mais novo e qual é o em uso, código de saída 2.
2. **Ubuntu 24.04 (Python 3.12).** `python3 instalador/instalar.py compose --simular --dominio nfse.exemplo.com.br --tls nenhum`
   mostra o plano e termina com código 0. Repita em uma VPS 22.04 (Python 3.10).
3. **Clone no Windows.** Com `git config --global core.autocrlf true`, clone o repositório e rode
   `git ls-files --eol docker/entrypoint-backend.sh instalador/instalar.py`: a coluna do diretório de trabalho deve ser `w/lf`.
   Depois, `docker compose up` deve subir o backend sem `exec format error` nem `bad interpreter`.
4. **Arquivo copiado com CRLF.** Salve um `.sh` com CRLF dentro do repositório e rode `git add` nele: o Git avisa que o CRLF
   será trocado por LF (`git show :caminho` não tem `\r`).

## O que os testes automatizados cobrem

| Garantia | Teste |
|---|---|
| O mínimo declarado é 3.10; 3.9 e anteriores recusados; 3.10, 3.12, 3.14 aceitos | `test_versao.py` |
| `instalar.py` num "Python 3.9": mensagem clara, código 2, **nenhum outro módulo do instalador importado**, sem `SyntaxError` | `test_versao.py` |
| O Python atual não é barrado pelo guarda | `test_versao.py` |
| Nenhum arquivo versionado de tipo sensível tem `\r` (falha com a lista dos arquivos e o conserto) | `test_quebras_de_linha.py` |
| Cada tipo (shell, entrypoint, Dockerfile, Nginx, `.modelo`, systemd, `.py`, `.env`) tem `eol=lf` no `.gitattributes` | `test_quebras_de_linha.py` |
| `text=auto` no resto; binários sem conversão | `test_quebras_de_linha.py` |
| Um arquivo com CRLF entra no repositório com LF | `test_quebras_de_linha.py` (repositório temporário) |
| A suíte inteira (113 testes) passa em **3.10, 3.12 e 3.14** | job `Instalador` do CI |

No CI, a falta do `git` é **falha**, não pulo (variável `CI`), para o teste de quebras de linha nunca sumir em silêncio.

## Mutações (17 de 17 detectadas)

Cada mutação estraga o que a correção protege e roda a suíte do instalador (Python 3.12, ou 3.10 onde a sintaxe importa).

| # | Mutação | Resultado |
|---|---|---|
| D1 a D8 | tirar o `eol=lf` de, um por vez: `*.sh`, `entrypoint*`, `Dockerfile*`, `*.conf`, `*.modelo`, `*.service`, `*.py`, `.env*` | detectadas (`.gitattributes` por tipo) |
| D9 | tirar `* text=auto` | detectada |
| D10 | tirar `*.woff2 binary` | detectada |
| D11 | entrypoint versionado com CRLF | detectada (arquivos versionados) |
| D12 | mínimo rebaixado para 3.9 | detectada |
| D13 | guarda de versão removido do `instalar.py` | detectada |
| D14 | guarda depois dos demais imports | detectada (módulos importados antes da mensagem) |
| D15 | mensagem sem o que fazer | detectada |
| D16 | o defeito original volta (`except A, B:`) | detectada (`SyntaxError` no 3.10 e no 3.12; `ruff format` com o alvo `py310` também reprova) |
| D17 | sintaxe do 3.12 (`type X = ...`) no instalador | detectada (3.10) |

Uma tentativa inicial do D11 não achou o trecho (o entrypoint começa com `#!/bin/sh`, não `bash`); corrigida a mutação, foi detectada.
