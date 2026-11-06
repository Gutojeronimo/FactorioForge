# Casos offline de qualidade

`run_quality_cases.py` mede geração com o dump de prototypes já carregado pelo ForgePlan. Não inicia Factorio, não lê nem altera saves e não grava blueprints.

`make_blueprint_string_example.py` imprime uma string sintética de uma entidade pelo serializador existente. É exemplo de formato, sem validação de importação no jogo.

| Caso | Receita/produto | Meta | Perfil |
|---|---|---:|---|
| `science-100` | `automation-science-pack` | 100/min | `balanced` |
| `science-1000` | `automation-science-pack` | 1.000/min | `balanced` |
| `science-10000` | `automation-science-pack` | 10.000/min | `balanced` |
| `science-10000-modular` | `automation-science-pack` | 10.000/min | `megabase` |
| `science-100000-modular` | `automation-science-pack` | 100.000/min | `megabase` |

Fixtures sintéticas de coprodutos, módulos, Pareto, geometria, capacidade, integridade de strings, Blueprint Books e particionamento em blocos estão em `tests/test_planning_quality.py`.
