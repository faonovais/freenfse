# Municípios do IBGE (`municipios_ibge.csv`)

Lista dos municípios brasileiros com o **código IBGE de 7 dígitos**, o nome e a UF. É dado público
do IBGE e alimenta a tabela `core.Municipio` pelo comando:

```bash
python manage.py carregar_municipios
```

O comando é idempotente (pode ser repetido) e o `docker/entrypoint-backend.sh` o executa a cada
subida do backend.

## Origem e data

| Item | Valor |
|---|---|
| Fonte primária | IBGE — Divisão Territorial Brasileira / códigos dos municípios (https://www.ibge.gov.br/explica/codigos-dos-municipios.php) |
| Cópia usada | Repositório público `kelvins/municipios-brasileiros` (licença MIT), arquivos `csv/municipios.csv` e `csv/estados.csv`, ramo `main` |
| Obtida em | **2026-10-30** |
| Registros | 5.571 municípios, 27 UFs (inclui o DF) |
| SHA-256 do `municipios.csv` de origem | `22bd03d004361329f69ddfa3f6c99cd53012aa53972a172e10b141288ad0b1fe` |
| SHA-256 do `estados.csv` de origem | `395c7b797b85592d71c686a0b537ba05349dee36c19b26a4b0d89494ff71448a` |
| SHA-256 do arquivo deste diretório | `de3ce3f6e34ff52bfa83c05ed068d5e8cc95aa35321fcdd8b9320edc16b9a5d6` |

> **Atenção:** no momento da obtenção os servidores do IBGE não estavam acessíveis a partir do
> ambiente de desenvolvimento, por isso a cópia veio do repositório acima, que é derivado do IBGE.
> Antes de uma implantação em produção, confira o arquivo contra a tabela oficial do IBGE (link na
> tabela acima) e, se houver divergência, atualize o arquivo e o SHA-256 deste documento.

## Transformação aplicada

O arquivo de origem tem mais colunas (latitude, longitude, DDD etc.), que o freenfse não usa. O
arquivo deste diretório é o resultado de:

```python
import csv

ufs = {r["codigo_uf"]: r["uf"] for r in csv.DictReader(open("estados.csv", encoding="utf-8-sig"))}
linhas = sorted(
    (r["codigo_ibge"], r["nome"].strip(), ufs[r["codigo_uf"]])
    for r in csv.DictReader(open("municipios.csv", encoding="utf-8-sig"))
)
# gravar "codigo_ibge,nome,uf" (UTF-8, LF) seguido de `linhas`
```

## Verificações de integridade

Os testes (`core/tests/test_municipios.py`) conferem, a cada execução:

- 5.571 registros, sem código repetido, 27 UFs e todos com 7 dígitos;
- os 2 primeiros dígitos do código batem com a UF informada;
- o dígito verificador do código IBGE confere, **exceto** em 9 códigos que o próprio IBGE
  atribuiu fora da regra (Bom Princípio do Piauí, Brejo do Piauí, Canavieira, Buriti de Goiás,
  Buritinópolis, Cônego Marinho, Ponto Chique, Coronel Barros e Quixaba). Por isso o carregador
  **não** exige o dígito verificador;
- municípios conhecidos conferem (por exemplo, 3550308 São Paulo/SP, 1721000 Palmas/TO e
  2101400 Balsas/MA).

## Licença da cópia

Os dados são públicos (IBGE). A compilação foi obtida de um repositório sob licença MIT, cujo
aviso é reproduzido abaixo, como exige a licença:

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
