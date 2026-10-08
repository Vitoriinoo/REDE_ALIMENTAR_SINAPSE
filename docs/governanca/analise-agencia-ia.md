# Análise de controle e acesso da IA

> Quanto a IA da Rede Alimenta pode **ver**, **decidir** e **fazer**, e o que impede que um erro ou um ataque vire dano.
> Lentes: **modelo 5C** (aula 7), **OWASP Top 10 for LLM 2025** (LLM06 *Excessive Agency*, LLM04 *Data and Model Poisoning*, LLM01 *Prompt Injection*), **MITRE ATLAS**.
> Código que implementa os controles: [`src/models/controle.py`](../../src/models/controle.py). Testes: [`tests/models/test_controle.py`](../../tests/models/test_controle.py).

---

## 1. Conclusão em uma frase

**A IA da plataforma tem agência zero:** ela só devolve recomendações para uma lista fechada de rótulos. Toda ação com efeito no mundo (gravar, aceitar, pagar, acionar transporte) é feita por regra no código ou por uma pessoa. O pior caso de um modelo errado ou atacado é uma **recomendação ruim**, que é limitada por regra, registrada e revertível.

## 2. Inventário de agência

| | NLP (texto → categoria) | M1 (prioridade) | M2 (risco de descarte) |
|---|---|---|---|
| **Lê** | Texto livre do doador, **depois** do guardrail | Categoria, armazenamento, tipo de doador, horas restantes, peso | Features do lote e do contexto logístico (sem dado pessoal) |
| **Não lê** | Identidade, endereço, documento | Nome, CPF/CNPJ, endereço, texto livre | Nome, CPF/CNPJ, endereço exato, texto livre |
| **Saída** | 1 de 6 categorias + 1 de 3 armazenamentos | 1 de 4 prioridades | Probabilidade em [0, 1] → risco alto (bool) pelo limiar |
| **Pode alterar** | Nada: é sugestão na tela | Nada: a regra aplica o piso de segurança | Nada: só habilita a **possibilidade** de pagar |
| **Quem confirma** | O **doador** confirma ou corrige | **Regra:** se a regra diz CRÍTICA, fica CRÍTICA | **Regra** (espera estourada) + **ONG/gestor** (aprovação do caixa) |
| **Se errar** | Doador corrige; as regras revalidam (PF × categoria, validade) | Prazo de aceite um pouco maior ou menor; caso crítico protegido | Gasto desnecessário do caixa (falso positivo) **ou** comida perdida (falso negativo) |
| **Se for atacado** | Pior caso: sugestão errada (sem ferramenta, sem execução) | Ataque exige adulterar o artefato: SHA-256 bloqueia o load | Idem M1; e o caixa tem teto e aprovação humana |
| **Desligado** | Doador escolhe a categoria sozinho | `prioridade_por_regra` | Heurística v0 (faltam < 4 h para o limite) |

## 3. Modelo 5C aplicado

| C | Pergunta da aula 7 | Resposta da plataforma | Evidência |
|---|---|---|---|
| **Contexto** | O que é instrução confiável e o que é dado externo? | O texto do doador é **sempre dado**. O classificador só escolhe rótulos fixos; não há prompt nem instrução. A resposta da BrasilAPI é validada por esquema | `guardrails.py`, `nlp.py`, `receita.py` |
| **Credenciais** | Quem é o agente e o que ele pode acessar? | Os modelos não têm credencial: não acessam banco, rede nem arquivo. A camada de controle é quem chama, e só com as features permitidas | `features.py` (lista de proibidas), `controle.py` |
| **Capacidades** | Quais ferramentas e ações estão disponíveis? | **Nenhuma**. Saída = recomendação. Tetos (caixa R$ 40/R$ 200), validade mínima e permissões estão fora do modelo | `logistica.py`, `validade.py` |
| **Controles** | Como detectar, interromper e investigar? | Saída validada contra lista fechada; fallback para regra; **desligamento por modelo**; toda chamada no log (modelo, versão, entradas, saída, confiança, latência); drift por PSI | `controle.py`, `registro.py`, `drift.py` |
| **Consciência** | Onde uma pessoa precisa decidir ou contestar? | Doador confirma a categoria; ONG aceita/recusa e inspeciona; gestor aprova acima do teto; admin aprova ONG e pode desligar modelos; correções viram feedback auditado | regras 3, 6.2.1, 9, 10.4 |

## 4. Riscos de excesso de agência que **não** existem aqui, e por quê

| Risco típico (OWASP LLM06) | Por que não se aplica |
|---|---|
| Modelo chama ferramenta com permissão demais | Não há ferramentas expostas ao modelo |
| Modelo decide pagamento | O pagamento acontece fora da plataforma; o caixa exige a ONG ou o gestor; o M2 só habilita a opção depois da espera |
| Instrução escondida no texto vira ação | O texto não é instrução; a saída é um rótulo de lista fechada |
| Modelo aprende com dado não validado | O feedback passa por validação (conta verificada, limite, quarentena, cota) e por portão humano |

## 5. Riscos residuais (honestos)

| Risco | Nível | Tratamento |
|---|---|---|
| Guardrail por padrões bloqueou só **4/10** ataques inéditos do conjunto B | Médio | Defesa principal é arquitetural (seção 1); o guardrail reduz a superfície |
| Recall do M2 no teste (83,4%) abaixo da meta de 85% | Médio | Monitorar drift; revisar limiar pelo portão do ciclo de feedback |
| Conjunto independente do NLP ainda não avaliado | Médio | O grupo preenche `tests/dados/avaliacao_independente_nlp.csv` |
| Ataque "lento" ao feedback (vários atores, pouco cada) | Baixo–Médio | Cota por ator + quarentena por perfil + revisão humana de amostra. **A demonstração mostrou que o portão por métrica NÃO pega um envenenamento diluído** (o candidato envenenado teria passado). A defesa que funciona é validar a **origem** do feedback (regras 10.4) |

## 6. Como desligar um modelo (procedimento)

1. Admin chama `Interruptores.definir(modelo, False, ator, motivo)`: o estado fica salvo em arquivo e sobrevive a reinício.
2. Alternativa no deploy: `REDE_ALIMENTA_IA_DESLIGADOS="nlp,descarte"`.
3. O evento `DESLIGAR_MODELO` vai para a trilha de auditoria com o motivo.
4. A partir daí, toda chamada registra `fonte=regra` e `motivo_fallback=modelo_desligado`, e o painel mostra quanto do tráfego está em fallback.
5. Religar exige o mesmo procedimento. Uma versão nova só entra pelo portão de promoção (regras 10.4).
