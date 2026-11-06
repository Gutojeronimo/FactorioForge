# Harness de validação no jogo (sub-projeto A) — design

**Data:** 2026-11-05 · **Estado:** rascunho para revisão do usuário · **Origem:** análise do projeto e decomposição A→B→C→D

## 1. Contexto e objetivo

O ForgePlan gera blueprints e simula offline, mas nenhum blueprint foi importado, construído ou medido no Factorio (K01, K11 em `docs/project/KNOWN-ISSUES-AND-LIMITATIONS.md`). Os próximos sub-projetos (B: grafo de fábrica + barramento; C: mundo/pesquisa; D: IA) dependem de saber se os números previstos batem com o jogo.

**Objetivo do A:** dado um blueprint e uma previsão do planejador (itens/s por produto), construí-lo num save descartável, rodá-lo por N ticks e devolver o que foi aceito, o que falhou e a taxa medida, para comparação automática.

**Fora de escopo:** gerar barramento (B), ler pesquisa do save (C), IA (D), trens.

## 2. Critérios de sucesso

1. Um comando importa um blueprint (string) num mapa de teste novo e produz um relatório JSON.
2. O relatório lista: entidades pedidas × construídas, entidades rejeitadas com motivo, produção medida por item (itens/s) na janela pós-warm-up, estado das máquinas (starved/blocked).
3. O Python compara medido × previsto e emite a razão e o veredito dentro de tolerância configurável.
4. Nenhum save, `mods` ou configuração do usuário é lido para escrita ou alterado.
5. Roda em vanilla (casos mínimos) e depois com a modlist ativa do usuário.
6. Reexecução do mesmo caso é determinística (mesma semente de mapa, mesmos ticks).

## 3. Restrições conhecidas

- Factorio em `C:\Program Files (x86)\Steam\steamapps\common\Factorio\bin\x64\factorio.exe`; mod bridge existente declara `factorio_version: 2.1`.
- `server.py` já isola execuções com `--config <ini com read-data/write-data>` e `--mod-directory <dir>` (linhas ~1669–1690). O harness reutiliza esse padrão.
- O dump de prototypes (347 MB) existe em `script-output/data-raw-dump.json`; os testes do harness não devem relê-lo inteiro (ver §6).
- Carregar 226 mods é lento; vanilla é o caminho padrão dos testes.

## 4. Arquitetura

```
Python (harness_runner)                     Factorio (processo isolado)
  ├─ prepara pasta .runtime/harness/<run>     ├─ --config / --mod-directory isolados
  ├─ escreve case.json (blueprint, ticks,     ├─ mod "forgeplan-harness" (control.lua)
  │   alimentação, previsão)                  │    ├─ cria superfície plana
  ├─ lança factorio (mapa novo, seed fixa)    │    ├─ importa blueprint e constrói
  ├─ aguarda término / timeout                │    ├─ alimenta entradas e energia
  └─ lê result.json de script-output ◄────────┘    ├─ roda N ticks, coleta estatísticas
       └─ compara com previsão → veredito          └─ grava result.json e encerra
```

### Componentes

| Unidade | Responsabilidade | Interface | Depende de |
|---|---|---|---|
| `harness/runner.py` | Preparar diretórios isolados, lançar Factorio, timeout, coletar resultado | `run_case(case) -> result` | exe do Factorio, mod harness |
| `factorio-mod/forgeplan-harness/` | Construir e medir dentro do jogo | lê `case.json`, grava `result.json` | API Lua do Factorio 2.1 |
| `harness/compare.py` | Previsto × medido, tolerância, veredito | `compare(prediction, result) -> report` | nenhuma |
| `harness/cases/*.json` | Casos mínimos versionados | schema do case | — |
| `harness/catalog_cache.py` | Cache compacto do dump (ver §6) | `load_catalog(fingerprint)` | dump |

Cada unidade é testável isoladamente: `compare` e `catalog_cache` em unittest puro; `runner` com Factorio falso (script que escreve um result.json fixo); o mod só no jogo real.

## 5. Contratos de dados

**case.json:** `{id, blueprint_string, ticks_warmup, ticks_measure, seed, feed: [{item|fluid, rate_per_s | infinite}], power: infinite, expected: {item: rate_per_s}, tolerance: {abs, rel}}`

**result.json:** `{case_id, factorio_version, mods_fingerprint, built: [{name, count}], rejected: [{name, position, reason}], measured: {item: rate_per_s}, machines: [{name, position, status_counts}], ticks_run, errors: []}`

**Entrega do case ao jogo:** scripts de controle não leem arquivos; o runner grava o case como string JSON dentro de `case_data.lua` na cópia do mod, e o mod usa `helpers.json_to_table`. O `result.json` sai por `helpers.write_file` em `script-output`.

Medição pós-warm-up usa as estatísticas de produção/consumo da superfície do próprio jogo (flow statistics) e o estado `entity.status` das máquinas amostrado em intervalos fixos.

## 6. Cache do catálogo

Ler os 347 MB a cada teste é inviável. `catalog_cache.py` extrai uma única vez, por fingerprint (versão do Factorio + mods + hash de `mod-settings`), apenas: receitas não ocultas, máquinas, módulos, beacons, esteiras/splitters/undergrounds, inserters e loaders **colocáveis e não ocultos**, com os campos de velocidade/energia/slots. Filtra entidades internas (por exemplo `*_panglia_fast_version`, `*BeltRamp`) por `hidden`, ausência de `minable`/item colocável e flags. Os testes do harness e do planejador usam esse cache.

## 7. Casos mínimos (vanilla, primeira entrega)

1. Montadora única com insumos infinitos → taxa = `crafting_speed / tempo`.
2. Mesma montadora com módulos de velocidade e produtividade → conferir bônus e consumo.
3. Linha de N montadoras alimentada por uma esteira → saturação por inserter/esteira.
4. Receita com fluido (entrada e saída).
5. Beacon afetando máquinas.

Cada caso tem previsão calculada pelo `production_math.py`/simulador atuais; o desvio inicial é o dado de calibração para o roadmap.

## 8. Tratamento de erros

- Timeout do Factorio ou saída sem `result.json` → `result` com `errors` e código de saída; nunca fica pendente.
- Entidade rejeitada na construção → listada em `rejected`, o caso é marcado como falha de serialização/colisão (não de throughput).
- Falha de carga de mod ou versão incompatível → erro explícito com o trecho relevante do log.
- Se o log registrar asserção/crash (por exemplo `LogisticSections::save`), o harness guarda o log e o blueprint exato, para fechar K06.

## 9. Segurança e isolamento

Pasta de escrita e `--mod-directory` próprios em `.runtime/harness/`; o mod harness é copiado para lá. Nenhum caminho do usuário fora disso é escrito. Nomes e caminhos derivados passam pela validação de containment já existente em `server.py`.

## 10. Estratégia de testes

- Unit: `compare`, `catalog_cache` (fixture pequena extraída do dump), geração do case.json, parsing do result.json.
- Runner com Factorio falso: timeout, saída vazia, resultado válido.
- Integração real (manual/CI local): casos de §7 contra o Factorio instalado; resultados guardados com versão do jogo e fingerprint.

## 11. Riscos e decisões em aberto

1. **Importar blueprint em script:** a API do Factorio 2.1 para criar entidades a partir da string (item de blueprint no inventário e `build_blueprint`) precisa ser confirmada na documentação 2.1 antes do plano; é a primeira tarefa do plano.
2. **Alimentar entradas:** baús infinitos via `infinity-chest` e `infinity-pipe` são o plano padrão; o mod modded pode exigir alternativa.
3. **Headless vs. janela:** tentar `--start-server-load-scenario`/`--benchmark` com o mod; se a API de superfície exigir cliente gráfico, usar `--benchmark` com `--benchmark-ticks`. A escolha final sai do primeiro experimento.
4. **Duração:** modlist completa pode levar minutos por caso; o harness expõe timeout configurável e roda vanilla por padrão.
5. Esta spec não define a tolerância numérica; ela nasce da primeira rodada de calibração.

## 12. Entregáveis

`harness/` (runner, compare, catalog_cache, cases), `factorio-mod/forgeplan-harness/`, testes em `tests/`, e um relatório da primeira rodada de calibração em `docs/project/`.
