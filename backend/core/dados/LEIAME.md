# Municípios do IBGE (`municipios_ibge.csv`)

Lista dos municípios brasileiros com o **código IBGE de 7 dígitos**, o nome e a UF. É dado público
do IBGE e alimenta a tabela `core.Municipio` pelo comando:

```bash
python manage.py carregar_municipios
```

O comando é idempotente (pode ser repetido, e atualiza o nome de um código já carregado) e o
`docker/entrypoint-backend.sh` o executa a cada subida do backend.

## Origem e data

O arquivo foi **conferido e regravado a partir da tabela oficial do IBGE** (Divisão Territorial
Brasileira, DTB), sem nenhuma outra fonte.

| Item | Valor |
|---|---|
| Fonte oficial | IBGE — DTB 2025 (`DTB_2025.zip`), planilha `RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.ods`, data-base **31/12/2025** |
| Endereço | https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/2025/DTB_2025.zip |
| Publicado pelo IBGE em | 26/03/2026 (cabeçalho `Last-Modified` do servidor) |
| Obtida em | **2026-10-31** |
| SHA-256 do `DTB_2025.zip` | `d077a0e48c36cf18bcc96268b4a436200c014c6b8522c1a62d894acaf39dad27` |
| SHA-256 da planilha de municípios | `a0606b9706c248138131511287e582a9293ba786096e0395192be36108d029fa` |
| Registros | 5.571 municípios, 27 UFs (inclui o DF) |
| SHA-256 do arquivo deste diretório | `71540779b62e9d2235fd62872b8defd6ef84f5190f9e393b9b08cf9aa6177bc1` |

### Resultado da conferência de 2026-10-31

| Resultado | Quantidade |
|---|---|
| Municípios na tabela oficial | 5.571 |
| Iguais ao arquivo anterior (código, nome e UF) | 5.540 |
| Diferentes (corrigidos) | 31, **todos só de grafia do nome**: o código e a UF já batiam |
| Faltantes no arquivo anterior | 0 |
| A mais no arquivo anterior | 0 |
| Depois da correção | 5.571 iguais, 0 diferenças |

Correções aplicadas (nome anterior → nome oficial):

| Código | Nome anterior | Nome oficial | UF |
|---|---|---|---|
| 1400605 | São Luiz | São Luiz do Anauá | RR |
| 1505551 | Pau d'Arco | Pau D'Arco | PA |
| 1708254 | Fortaleza do Tabocão | Tabocão | TO |
| 2304277 | Ererê | Ereré | CE |
| 2400208 | Açu | Assú | RN |
| 2401206 | Arês | Arez | RN |
| 2401305 | Augusto Severo (Campo Grande) | Campo Grande | RN |
| 2405306 | Januário Cicco (Boa Saúde) | Januário Cicco | RN |
| 2408409 | Olho-d'Água do Borges | Olho d'Água do Borges | RN |
| 2512606 | Quixabá | Quixaba | PB |
| 2613107 | São Caetano | São Caitano | PE |
| 2613800 | São Vicente Ferrer | São Vicente Férrer | PE |
| 2800100 | Amparo de São Francisco | Amparo do São Francisco | SE |
| 2802601 | Gracho Cardoso | Graccho Cardoso | SE |
| 2902054 | Araças | Araçás | BA |
| 2917334 | Iuiú | Iuiu | BA |
| 2922250 | Muquém de São Francisco | Muquém do São Francisco | BA |
| 2928505 | Santa Teresinha | Santa Terezinha | BA |
| 3105509 | Barão de Monte Alto | Barão do Monte Alto | MG |
| 3122900 | Dona Eusébia | Dona Euzébia | MG |
| 3145455 | Olhos d'Água | Olhos-d'Água | MG |
| 3147808 | Passa-Vinte | Passa Vinte | MG |
| 3165206 | São Thomé das Letras | São Tomé das Letras | MG |
| 3200706 | Atilio Vivacqua | Atílio Vivácqua | ES |
| 3506607 | Biritiba-Mirim | Biritiba Mirim | SP |
| 3516101 | Florínia | Florínea | SP |
| 3522158 | Itaóca | Itaoca | SP |
| 4206108 | Grão Pará | Grão-Pará | SC |
| 4209607 | Lauro Muller | Lauro Müller | SC |
| 4216057 | São Cristovão do Sul | São Cristóvão do Sul | SC |
| 5107800 | Santo Antônio do Leverger | Santo Antônio de Leverger | MT |

## Como conferir de novo (antes de uma implantação em produção)

1. Baixe o arquivo oficial (o comando abaixo não acessa a rede) e guarde o SHA-256:

   ```bash
   curl -fsSL -o DTB.zip "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/<ano>/DTB_<ano>.zip"
   sha256sum DTB.zip
   ```

2. Compare (relatório de iguais, diferentes, faltantes e a mais):

   ```bash
   python manage.py comparar_municipios_ibge DTB.zip
   ```

3. Se houver diferença, regrave o CSV a partir da fonte oficial e atualize este documento (origem,
   data, SHA-256 do zip, da planilha e do CSV) e o SHA-256 em `core/tests/test_municipios.py`:

   ```bash
   python manage.py comparar_municipios_ibge DTB.zip --gravar
   ```

O comando lê a planilha sem resolver entidades XML nem acessar a rede, recusa linhas com UF que
não bate com o código e grava o CSV em ordem de código, UTF-8, LF.

## Verificações de integridade

Os testes (`core/tests/test_municipios.py` e `core/tests/test_municipios_oficiais.py`) conferem, a
cada execução:

- 5.571 registros, sem código repetido, 27 UFs e todos com 7 dígitos;
- o SHA-256 do arquivo é o registrado neste documento;
- os 2 primeiros dígitos do código batem com a UF informada;
- o dígito verificador do código IBGE confere, **exceto** em 9 códigos que o próprio IBGE
  atribuiu fora da regra (Bom Princípio do Piauí, Brejo do Piauí, Canavieira, Buriti de Goiás,
  Buritinópolis, Cônego Marinho, Ponto Chique, Coronel Barros e Quixaba). Por isso o carregador
  **não** exige o dígito verificador;
- municípios conhecidos conferem (por exemplo, 3550308 São Paulo/SP, 1721000 Palmas/TO e
  2101400 Balsas/MA) e as grafias corrigidas pela conferência (por exemplo, 4209607 Lauro Müller/SC);
- o leitor e a comparação com a tabela oficial, com uma planilha de teste montada em código.

## Histórico

A primeira versão deste arquivo (2026-10-30) foi montada a partir do repositório público
`kelvins/municipios-brasileiros` (licença MIT), porque os servidores do IBGE não estavam acessíveis
no ambiente de desenvolvimento naquele momento (SHA-256 do arquivo daquela versão:
`de3ce3f6e34ff52bfa83c05ed068d5e8cc95aa35321fcdd8b9320edc16b9a5d6`). Em 2026-10-31, com o acesso liberado, o arquivo foi conferido e regravado a partir
da tabela oficial acima. O aviso da licença daquela cópia é mantido por transparência:

```
MIT License

Copyright (c) 2016 Kelvin S. do Prado

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
