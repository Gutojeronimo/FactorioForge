# Integração com IA

## Estado observado

| Capacidade | Estado | Evidência |
|---|---|---|
| Consultar Ollama local e listar modelos instalados | Implementado | [server.py:572](../../server.py#L572), [Program.cs:312](../../desktop/Program.cs#L312) |
| Pedir ao modelo uma sugestão de máquinas por linha | Implementado | [server.py:596](../../server.py#L596) |
| Planejar taxas, máquinas, equipamentos e topologia com IA | Ausente no fluxo atual | O prompt limita o modelo a escolher colunas; construção e validação permanecem determinísticas ([server.py:596](../../server.py#L596), [server.py:1484](../../server.py#L1484)) |
| Usar provedor remoto ou modelo fora da máquina local | Ausente por validação | Somente HTTP em loopback é aceito ([server.py:572](../../server.py#L572)) |
| Medir qualidade relativa das sugestões por modelo | Não verificado | Não há avaliação comparativa de modelos no fluxo de geração. |

A IA é uma etapa opcional de escolha geométrica. Ela não determina a meta de produção, a receita, o número de máquinas, módulos, taxas de transporte ou entidades físicas do blueprint.

## Fluxo

WPF → processo JSON-lines native_bridge.py → planejamento determinístico em server.py → chamada opcional ao Ollama → construção/simulação/validação determinísticas → resultado JSON-lines para a interface.

O WPF consulta /api/tags ao iniciar e periodicamente quando não está ocupado. O usuário também pode atualizar a lista manualmente na aba IA. A interface envia modelo, limite de tempo, instruções livres e opção de fallback junto ao comando de geração. Evidências: [Program.cs:197](../../desktop/Program.cs#L197), [Program.cs:222](../../desktop/Program.cs#L222), [Program.cs:312](../../desktop/Program.cs#L312), [Program.cs:426](../../desktop/Program.cs#L426), [native_bridge.py:94](../../native_bridge.py#L94).

## Endpoint e contrato

O endereço configurado precisa usar HTTP, host 127.0.0.1, localhost ou ::1, sem credenciais, caminho, query ou fragmento. A verificação de disponibilidade consulta /api/tags com timeout de 5 segundos. Isso restringe o app ao serviço local; não há integração observada com API remota, chave de nuvem ou seleção de família de modelos além dos nomes retornados por Ollama. [server.py:572](../../server.py#L572), [server.py:579](../../server.py#L579)

A sugestão usa /api/chat, resposta não streaming, think=false e formato JSON com columns inteiro e note textual. A chamada define temperatura 0,1, contexto de 4096 tokens e até 192 tokens previstos. O timeout é limitado entre 15 e 600 segundos; a interface usa 120 segundos como padrão. O resultado é limitado a 1–20 colunas, ou até o número de máquinas se ele for menor. [server.py:596](../../server.py#L596), [Program.cs:426](../../desktop/Program.cs#L426)

## Contexto entregue ao modelo

O prompt contém receita e produto escolhidos, contagem de máquinas já calculada, produção resultante, taxas de insumos e saídas por minuto, perfil de fábrica, contexto local de padrões de metalurgia, instruções do usuário e intervalo permitido de colunas. As instruções são limitadas a 2.000 caracteres. O modelo deve preferir fileiras equilibradas e compactas. O prompt diz que correias, inserters, postes, canos e combinadores serão colocados e verificados pelo planejador. O campo note é limitado a 500 caracteres. [server.py:596](../../server.py#L596), [server.py:1331](../../server.py#L1331)

## Propriedade da decisão e fallback

O planejador calcula antes da chamada a receita, o produto, a máquina, os efeitos/módulos, quantidade de máquinas e necessidades logísticas. Sem modelo, a etapa retorna layout automático. Com modelo, a sugestão de colunas vira um candidato; o código determinístico constrói as entidades. A análise física e temporal continua no modo de esteiras. [server.py:1331](../../server.py#L1331), [server.py:1484](../../server.py#L1484), [server.py:1530](../../server.py#L1530)

Se a chamada falhar por rede, resposta inválida ou parse, a opção “Usar perfil configurado se a IA falhar” permite continuar e registra a mensagem em ai.error. Com fallback desativado, a falha interrompe a geração. O resultado inclui modelo, layout, flag de uso, erro, nota e duração. [server.py:1484](../../server.py#L1484), [server.py:1647](../../server.py#L1647), [FactorySettings.cs:32](../../desktop/FactorySettings.cs#L32)

Um modelo ausente não impede gerar um blueprint. A UI mostra conexão e modelos encontrados. O tempo exibido e o cancelamento pertencem à operação completa de geração, não a uma chamada isolada de IA. [Program.cs:312](../../desktop/Program.cs#L312), [Program.cs:426](../../desktop/Program.cs#L426), [Program.cs:232](../../desktop/Program.cs#L232)

## Limitações e evolução

- Não há avaliação automática de qualidade, latência ou reprodutibilidade das sugestões por modelo.
- O texto de instruções é livre, mas a resposta permitida continua restrita a colunas e nota.
- O modelo não observa a prévia, não recebe feedback do simulador e não escolhe novamente após avaliação ruim.
- A duração registrada cobre a etapa de decisão de IA; não é o tempo total de geração.
- Uma resposta parseável ainda pode ser ajustada ou substituída pela construção determinística.
- Não há suporte observado a IA para escolha de tecnologia pesquisada, roteamento de fluidos, roteamento espacial de esteiras ou otimização conjunta de produtos.

Recomendação: registrar prompts e decisões reproduzíveis; comparar sugestões contra os scores e simulações físicas atuais; só depois ampliar o contrato da IA. Qualquer ampliação deve preservar a validação determinística do blueprint. Esses itens são roadmap, não capacidades atuais. Para os algoritmos determinísticos, consulte [PRODUCTION-ENGINE.md](PRODUCTION-ENGINE.md) e [OPTIMIZATION-ENGINE.md](OPTIMIZATION-ENGINE.md).
