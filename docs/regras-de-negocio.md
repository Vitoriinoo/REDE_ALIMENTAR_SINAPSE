# Rede Alimenta IA: Regras de Negócio

> **Status:** v1.1, regras validadas pelo grupo em 2026-09-23 (v1.1: orientação de refrigeração, turno noturno, inspeção na entrega e rodadas).
> Este documento é a **fonte de verdade** do gerador de dados (`src/data`), dos modelos (`src/models`) e da Matriz STRIDE (`docs/stride`).

---

## 1. Visão geral

A Rede Alimenta IA conecta **excedentes de alimentos** de doadores a **ONGs** na Grande São Paulo e resolve também o **transporte**, aproveitando capacidade logística ociosa (frete de retorno).

A IA **recomenda**. As pessoas **decidem** as ações de impacto. Toda regra crítica fica **no código**, fora do modelo.

**Princípios de projeto** (tirados das aulas de Cibersegurança em IA):

| Princípio | Como aparece no sistema |
|---|---|
| Recomendação antes de execução | A IA sugere a ONG e o transporte, e um humano aceita |
| Autorização fora do modelo | Permissões, tetos e validade mínima são regras no código |
| Saída da IA não é comando | A categoria sugerida pelo NLP é confirmada pelo doador |
| Minimização de dados (LGPD) | Os modelos nunca recebem CPF, nome ou endereço exato |
| Segregação de funções | Quem pede dinheiro do caixa nunca é quem aprova |
| Rastreabilidade | Toda decisão gera log auditável (seção 10) |

---

## 2. Recorte geográfico

8 municípios da RMSP, divididos em **15 regiões**:

| Município | Regiões |
|---|---|
| São Paulo (capital) | 8 macrorregiões da Prefeitura: Centro, Oeste, Norte 1, Norte 2, Sul 1, Sul 2, Leste 1, Leste 2 (96 distritos → 32 subprefeituras → 8 macrorregiões) |
| Guarulhos, Osasco, Santo André, São Bernardo do Campo, São Caetano do Sul, Diadema, Mauá | 1 região por município |

> Por que 8 macrorregiões e não 5 zonas: a "Zona Leste" inteira mistura Mooca/Tatuapé (Leste 1, 9,6% de setores vulneráveis) com Guaianases/Cidade Tiradentes (Leste 2, 32,7%). Agregar por zona esconderia justamente a desigualdade que o mapa de calor precisa mostrar.

### 2.1 Vulnerabilidade: IPVS 2022 (Fundação SEADE)

- **Fonte:** IPVS 2022 por setor censitário (36.847 setores no recorte), baixado e validado por SHA-256 pelo script `src/data/curadoria_ipvs.py`.
- **Indicador por região:** `pct_vulneravel` = % dos setores classificados nos **grupos 5 e 6** (vulnerabilidade alta e muito alta).
- **Índice regional:** `indice_vulnerabilidade` = normalização min-max de `pct_vulneravel`. É usado **só em KPIs e no mapa de calor**.
- **Ranking de ONGs (6.1):** usa o **grupo IPVS do setor censitário onde a ONG atua**, não o índice da região. Assim uma ONG num bolsão vulnerável dentro de uma região rica (ex.: São Caetano, índice regional 0) é reconhecida.
- **Limitação:** o arquivo não traz população por setor, então a proporção é de **setores**, não de pessoas. É uma aproximação razoável, porque o IBGE dimensiona os setores com número de domicílios semelhante.
- **Localização realista:** doadores, ONGs e hubs do dataset simulado são posicionados em **centroides de setores censitários reais** (`data/reference/setores_rmsp.csv`).

| Região | % setores vulneráveis | Índice |
|---|---|---|
| SP - Sul 2 | 42,6% | 1,00 |
| Diadema | 38,5% | 0,90 |
| Guarulhos | 33,5% | 0,79 |
| SP - Leste 2 | 32,7% | 0,77 |
| Mauá | 31,5% | 0,74 |
| SP - Norte 2 | 25,1% | 0,59 |
| Osasco | 22,4% | 0,53 |
| São Bernardo do Campo | 21,8% | 0,51 |
| Santo André | 16,3% | 0,38 |
| SP - Norte 1 | 16,1% | 0,38 |
| SP - Leste 1 | 9,6% | 0,23 |
| SP - Sul 1 | 9,4% | 0,22 |
| SP - Oeste | 6,4% | 0,15 |
| SP - Centro | 1,9% | 0,04 |
| São Caetano do Sul | 0,0% | 0,00 |

> Validação cruzada: a ordem é coerente com o IDHM 2010 (PNUD/Atlas Brasil). São Caetano tem o maior IDHM do recorte (0,862) e Guarulhos o menor entre os confirmados (0,763).

---

## 3. Atores e perfis de acesso

| Perfil | Quem é | Pode | Não pode |
|---|---|---|---|
| **Doador PJ** | Restaurante, mercado, padaria, hortifruti, indústria (CNPJ) | Cadastrar lotes de **qualquer categoria**, acompanhar status | Ver dados de outras doações, escolher a ONG |
| **Doador PF** | Pessoa física (CPF) | Cadastrar lotes **só de Não perecível e Hortifruti** | Doar Preparado, Refrigerado, Congelado ou Padaria |
| **ONG** | Associação/fundação com CNPJ **aprovada por admin** | Aceitar/recusar lotes, confirmar recebimento, **solicitar** uso do caixa | Aprovar gasto do caixa, ver dados de outras ONGs |
| **Transportador** | Voluntário, motorista de retorno, transportadora parceira | Aceitar/recusar coletas, confirmar coleta e entrega | Ver o endereço exato antes de aceitar |
| **Gestor do caixa** | Pessoa **externa às ONGs** (plataforma ou parceiro) | Aprovar/recusar gastos acima do teto | Ser vinculado a uma ONG, cadastrar lotes |
| **Admin** | Equipe da plataforma | Aprovar ONGs, cadastrar hubs, tratar escaladas | Aprovar gastos do caixa (segregação de funções) |

**Regra:** um usuário tem exatamente **um perfil**. Contas diferentes para papéis diferentes.

---

## 4. Lotes de alimentos

### 4.1 Categorias e quem pode doar

| Categoria | Exemplos | PJ | PF | Cadeia fria |
|---|---|:-:|:-:|:-:|
| Preparado | Marmitas, refeições prontas | ✅ | ❌ | ✅ |
| Refrigerado | Laticínios, frios | ✅ | ❌ | ✅ |
| Congelado | Carnes, congelados | ✅ | ❌ | ✅ |
| Hortifruti | Frutas, verduras, legumes | ✅ | ✅ | ❌ |
| Padaria | Pães, bolos | ✅ | ❌ | ❌ |
| Não perecível | Grãos, enlatados, industrializados lacrados | ✅ | ✅ | ❌ |

> Base legal: a **Lei 14.016/2020** regula a doação de excedentes por estabelecimentos. Alimento preparado só vem de PJ, que responde sanitariamente.
> PF não doa Padaria: o produto artesanal caseiro tem o mesmo risco do preparado.

### 4.2 Validade efetiva: calculada pelo sistema

O doador **não digita a validade** dos itens de cadeia fria (Preparado, Refrigerado, Congelado). Ele informa:
- **hora do preparo** (Preparado) ou **validade do rótulo** (Refrigerado/Congelado);
- **armazenamento atual:** `refrigerado` · `congelado` · `ambiente`;
- se está em `ambiente`: **desde que horas** está fora da refrigeração.

O sistema calcula a **validade efetiva** por regra no código:

| Situação | Validade efetiva |
|---|---|
| Preparado refrigerado (≤ 5 °C desde o preparo) | `preparo + 72 h` |
| Preparado em ambiente | `preparo + 3 h` |
| Refrigerado/Congelado em refrigeração | validade do rótulo |
| Refrigerado/Congelado **fora** da refrigeração | `min(rótulo, saída_da_refrigeração + 3 h)` |
| Hortifruti, Padaria, Não perecível | validade informada pelo doador |

> A janela de ambiente (`JANELA_AMBIENTE = 3 h`) é um parâmetro único no código.
> Motivo: a validade digitada é **entrada não confiável**. Calcular no sistema evita erro e má-fé (linha de *Tampering* na STRIDE).

### 4.3 Validade mínima para aceite

Vale sobre a **validade efetiva restante**. Abaixo do mínimo, o cadastro é **bloqueado** e o doador recebe orientação (compostagem, descarte correto).

| Categoria / situação | Validade efetiva restante mínima |
|---|---|
| Preparado refrigerado | 4 h |
| Preparado em ambiente | 1 h 30 (entra na **rota expressa**, seção 7.5) |
| Refrigerado / Congelado em refrigeração | 12 h / 24 h |
| Refrigerado / Congelado fora da refrigeração | 1 h 30 (entra na **rota expressa**) |
| Hortifruti | 24 h |
| Padaria | 12 h |
| Não perecível | 7 dias |

### 4.4 Cadastro com texto livre (NLP)

1. O doador descreve o lote em texto livre, por exemplo: *"30 marmitas de arroz, feijão e frango feitas hoje ao meio-dia"*.
2. **Guardrail de entrada:** limite de tamanho e remoção de padrões suspeitos antes de o texto chegar ao modelo.
3. Um modelo **Hugging Face de embeddings multilíngue** compara o texto com **exemplos escritos à mão por categoria** (`src/models/exemplos_nlp.py`) e sugere **categoria** e **armazenamento**. O classificador só escolhe rótulos de uma lista fixa.
   > Histórico: a primeira versão usava zero-shot por NLI e ficou em 49% de acurácia e 3,3 s por texto. A troca para similaridade levou a 76% e 4,6 ms (ver `reports/avaliacao_nlp.json`).
4. **O doador confirma ou corrige.** A sugestão nunca é gravada sem confirmação.
5. A regra da seção 4.1 (PF × categoria) é revalidada **no código** depois da confirmação.

---

## 5. Modelo 1: Prioridade do lote

**Quando roda:** no cadastro, logo após a confirmação da categoria.
**Entradas:** **só** dados informados pelo doador (categoria, armazenamento, validade restante, peso, tipo de doador).
**Saída:** `CRÍTICA` · `ALTA` · `MÉDIA` · `BAIXA`.
**Métrica-guia:** macro-F1 + **recall da classe CRÍTICA ≥ 90%**.

### 5.1 Regra de rotulagem (dataset simulado)

Faixas de **validade efetiva restante** (seção 4.2):

| Categoria | CRÍTICA | ALTA | MÉDIA | BAIXA |
|---|---|---|---|---|
| Preparado em ambiente | **sempre** | — | — | — |
| Preparado refrigerado | < 12 h | 12–24 h | 24–48 h | > 48 h |
| Qualquer item de cadeia fria fora da refrigeração | **sempre** | — | — | — |
| Refrigerado | < 24 h | 24–48 h | 48–96 h | > 96 h |
| Congelado | < 3 d | 3–7 d | 7–15 d | > 15 d |
| Hortifruti | < 36 h | 36–72 h | 3–5 d | > 5 d |
| Padaria | < 18 h | 18–36 h | 36–72 h | > 72 h |
| Não perecível | nunca | 7–15 d | 15–30 d | > 30 d |

**Ajuste da regra:**
- Peso > 50 kg: **sobe um nível** (o volume grande é mais difícil de alocar).

> O armazenamento não é mais um "ajuste". Ele entra direto na validade efetiva (4.2), o que é mais fiel à segurança alimentar.

**Ruído humano:** ~8–10% dos rótulos são alterados em ±1 nível, simulando a discordância entre triadores. Assim se evita a circularidade (o modelo reaprender a fórmula e dar ~100% de acurácia).

---

## 6. Matching Doador × ONG

### 6.1 Ranking das ONGs

Só entram no ranking as ONGs **aprovadas**, com **capacidade disponível** e **compatíveis** com a categoria (ex.: sem refrigeração, a ONG não recebe Refrigerado).

```
score = w1·proximidade + w2·capacidade_disponível + w3·vulnerabilidade_setor (IPVS) + w4·compatibilidade
```

**Pesos:** w1 = 0,35 (proximidade) · w2 = 0,20 (capacidade) · w3 = 0,30 (vulnerabilidade) · w4 = 0,15 (compatibilidade). Os pesos ficam versionados no código e são auditáveis.

> Decisão de impacto social: a vulnerabilidade tem peso próximo ao da distância. Às vezes a comida vai um pouco mais longe para chegar a quem mais precisa.

### 6.2 Fluxo de aceite

1. O sistema notifica a **1ª ONG** do ranking.
2. Se ela não responder dentro do prazo, passa para a próxima:

| Prioridade | Prazo de aceite |
|---|---|
| CRÍTICA | 12 min |
| ALTA | 25 min |
| MÉDIA | 75 min |
| BAIXA | 5 h |

3. **Após 3 recusas ou expirações**, o lote escala para o **Admin**.
4. Se ainda assim ninguém aceitar, o sistema faz **nova rodada a cada 4 h**, dentro do horário de operação (7 h–21 h), até o limite de consumo do lote. A rota expressa não tem nova rodada (ver 7.5).
5. O endereço exato do doador só é liberado **depois do aceite**.

### 6.2.1 Inspeção na entrega

A ONG **confere o lote na porta e pode recusá-lo** (produto amassado, estufado, passado). A recusa fica registrada em log com o motivo. É um direito da ONG e uma proteção para quem vai consumir.

### 6.3 Verificação de ONG

- CNPJ **ativo** com natureza jurídica de associação/fundação (validação simulada).
- **Aprovação manual por Admin** antes de receber qualquer lote.
- Só ONG aprovada pode solicitar uso do caixa solidário.

### 6.4 Cadastro operacional da ONG

Para entrar no matching, a ONG informa:
- **Capacidade diária** (kg) e se possui **refrigeração** (e capacidade refrigerada);
- **Turnos em que serve refeição** (`café` · `almoço` · `jantar` · `noturno`). O turno `noturno` (20 h–23 h) é o dos coletivos que distribuem refeições à noite, por exemplo à população em situação de rua. É obrigatório para receber lotes da rota expressa (7.5): o lote só vai para uma ONG cujo próximo turno comece antes de a validade efetiva vencer;
- **Categorias aceitas** e **região atendida**.

---

## 7. Transporte

### 7.1 Modalidades

| Modalidade | Custo | Frota simulada | Observação |
|---|---|---|---|
| ONG / voluntário retira | Grátis | 70 voluntários | Disponibilidade esporádica |
| Doador entrega | Grátis | — | Até a ONG ou até um hub |
| Motorista autônomo (retorno) | Grátis | 65 motoristas | Aceita coleta no caminho de volta |
| Transportadora parceira | Grátis | 25 empresas | Rotas fixas A→B; algumas com **baú refrigerado** |
| Entregador de app | **Pago pelo caixa** | Pool externo simulado | Integração simulada (estilo UberEats / 99food / Keeta) |

### 7.2 Cascata de escolha

1. Tenta as **modalidades gratuitas** primeiro.
2. O entregador **pago** só é acionado se as duas condições valerem:
   - nenhuma modalidade gratuita aceitou dentro do prazo, **E**
   - o **Modelo 2 prevê alto risco de descarte**.

| Prioridade | Espera pelo gratuito antes do pago |
|---|---|
| CRÍTICA | 18 min |
| ALTA | 38 min |
| MÉDIA | 2 h 30 |
| BAIXA | **nunca paga** |

> No **histórico simulado** (antes do Modelo 2 existir), o "risco alto de descarte" foi decidido por uma heurística operacional: faltam menos de 4 h para o limite de consumo. Em produção, o **Modelo 2 substitui essa heurística**.

### 7.3 Cadeia fria

Lotes de Preparado, Refrigerado e Congelado **só** podem ir:
- em **veículo refrigerado**, **OU**
- em trajeto de **até 60 min** sem refrigeração.

Transportadores que não atendem a regra são **filtrados antes** de receberem a oferta.

### 7.4 Pontos de entrega

- **Porta a porta:** coleta no doador (ex.: restaurante que não consegue sair).
- **Hub:** ~40 pontos **pré-cadastrados e validados por Admin** (sedes de ONGs, CEUs, comércios parceiros). O sistema escolhe o hub que minimiza *desvio de rota do motorista + deslocamento do doador*.
- **Doador PF:** o endereço exato nunca é exposto antes do aceite. O hub é a opção preferencial.

### 7.5 Rota expressa

Para lotes com validade efetiva curta: **preparado em ambiente** ou **item de cadeia fria fora da refrigeração**.

| Regra | Valor |
|---|---|
| Validade efetiva restante mínima | 1 h 30 |
| Prioridade | Sempre **CRÍTICA** |
| Entrega | Só **porta a porta** (sem hub, para não haver parada intermediária) |
| Trajeto máximo | **30 min** |
| ONGs elegíveis | Só as que **servem refeição no mesmo turno** |
| Transporte | Cascata normal de CRÍTICA. Se o Modelo 2 prevê descarte, o entregador pago entra após 18 min |

**Sem ONG viável na janela: orientação de refrigeração**

1. O sistema orienta o doador a **refrigerar imediatamente**.
2. Se o doador refrigerar **dentro da janela de 3 h**, o lote sai da rota expressa com validade conservadora de **`preparo + 48 h`** (Preparado) ou **`min(rótulo, refrigeração + 48 h)`** (Refrigerado/Congelado), e volta ao fluxo normal. É menos que as 72 h de quem refrigerou desde o preparo, porque o alimento já passou tempo em temperatura ambiente.
3. Se não refrigerar (ou refrigerar fora da janela), o lote é **cancelado com orientação de descarte** em vez de ser entregue com risco sanitário.

> Por que existe: na simulação, sem essa regra, 88% dos lotes da rota expressa eram perdidos, e 100% entre 20 h e 24 h (restaurante fechando sem ONG servindo refeição até a manhã). Com turno noturno + orientação, a perda da rota expressa caiu para ~39%.

---

## 8. Modelo 2: Risco de descarte

**Quando roda:** depois do Modelo 1, com o **contexto logístico** do momento.
**Saída:** probabilidade de o lote **não ser salvo** (descarte).
**Métrica-guia:** **recall da classe descarte ≥ ~85%** com piso de precisão. O threshold é ajustado conscientemente, porque:
- **Falso negativo** = comida perdida (custo social alto).
- **Falso positivo** = gasto desnecessário do caixa.

**Features (sem dados pessoais):** categoria, armazenamento, rota expressa, prioridade prevista, horas até vencer, peso, segmento/tipo de doador, **doador tem refrigeração**, região, hora do dia, dia da semana, mês, feriado, nº de ONGs compatíveis num raio de 10 km, distância da ONG mais bem ranqueada, nº de transportadores ativos no raio, disponibilidade de veículo refrigerado.

**Rótulo (simulação do processo, não fórmula):** o lote é **descartado** se:
- nenhuma ONG aceitar, **OU**
- `tempo_match + tempo_até_coleta + tempo_trajeto > validade_restante`, **OU**
- houver quebra de cadeia fria na entrega, **OU**
- a ONG recusar na inspeção (6.2.1), **OU**
- o lote da rota expressa não for refrigerado após a orientação (7.5).

Os tempos são sorteados a partir de distribuições que dependem de hora, dia, região e frota disponível, com fatores que o modelo **não vê** (ver 8.1).

### 8.1 Premissas da simulação

| Premissa | Como entra na simulação | O Modelo 2 vê? |
|---|---|---|
| **Descompasso espacial** | Doadores PJ concentrados em setores de baixa vulnerabilidade (áreas comerciais), PF espalhados. ONGs concentradas em setores dos grupos 5–6 | Indiretamente (distância, nº de ONGs no raio) |
| **Horários por segmento** | Tendências, não janelas fixas: ~75% perto dos picos do segmento, ~25% espalhados no horário de funcionamento. Restaurante: pós-almoço e fechamento. Padaria: fim do dia. Mercado/hortifruti: reposição de manhã e fim de tarde. Indústria: horário comercial. PF: noite e fim de semana | Sim (hora, dia) |
| **Chuva** | Dias de chuva reduzem a disponibilidade de voluntários e motos e aumentam o tempo de trajeto | **Não** (fator latente) |
| **Trânsito** | Picos de 7–10 h e 17–20 h aumentam o tempo de trajeto | Indiretamente (hora) |
| **Sazonalidade** | Mais doações em dezembro e nos fins de semana (restaurantes), menos em feriados prolongados | Sim (dia/mês) |
| **Recusa da ONG por contexto** | A probabilidade de recusa sobe perto da capacidade diária e fora do horário de funcionamento | Parcialmente (capacidade no raio) |
| **Capacidade das ONGs** | Mediana de ~60 kg/dia: a capacidade vira gargalo em picos e em lotes grandes da indústria | Indiretamente (nº de ONGs compatíveis) |
| **Inspeção na entrega** | Recusa com probabilidade que cresce com a fração da vida útil consumida até a entrega, maior para hortifruti, padaria e refrigerado, multiplicada por uma **qualidade latente** do lote | **Não** (qualidade latente) |
| **Adesão à orientação de refrigeração** | Doador com geladeira refrigera com ~70% de probabilidade; sem geladeira, não consegue | Parcialmente (`doador_tem_refrigeracao`) |

> Os fatores que o modelo não vê são intencionais: produzem incerteza realista e impedem que o Modelo 2 chegue a 100%.

---

## 9. Caixa solidário

- A plataforma **não guarda dinheiro** nem processa pagamentos. Mantém só um **livro-caixa transparente**: aportes, entregas pagas e comprovantes.
- O pagamento acontece **fora** da plataforma (ONG ou parceiro paga direto no app de entrega).
- **Sem lucro:** só o custo do entregador.

| Valor | Aprovação |
|---|---|
| Até **R$ 40 por entrega** e até **R$ 200 por dia por ONG** | O sistema recomenda e a ONG confirma |
| Acima de qualquer teto | **Gestor do caixa** aprova (externo à ONG) |

---

## 10. Rastreabilidade (logs)

Toda decisão relevante gera um registro auditável, **sem dados pessoais em claro**:

```json
{
  "componente": "matching-v1",
  "ator": "ong:3f9a…",
  "acao": "ACEITAR_LOTE",
  "lote_id": "L-000123",
  "modelo": "prioridade-v1",
  "predicao": "CRITICA",
  "fonte": "regras-de-negocio-v0.1",
  "horario": "2026-09-23T19:42:00-03:00"
}
```

---

## 11. Privacidade (LGPD): regras de base

- **CPF/CNPJ** são armazenados só como **HMAC-SHA256 com chave secreta** (nunca em claro). A chave fica num cofre de segredos, fora do código e do banco.
  > Por que não SHA-256 com salt: existem só ~10⁹ CPFs válidos. Um hash sem segredo é revertido por **força bruta** em minutos (aula 3). Com HMAC, sem a chave o hash não serve para nada.
- **Endereço de PF:** só o centroide do bairro até o aceite do match.
- **Modelos de IA** nunca recebem nome, CPF, telefone ou endereço exato.
- **Retenção:** dados de contato apagados/anonimizados 12 meses após a última atividade. Métricas agregadas são mantidas.

---

## 12. KPIs do dashboard

| KPI | Cálculo |
|---|---|
| kg salvos | Soma do peso dos lotes com entrega confirmada |
| Refeições geradas por região | kg salvos × fator kg→refeição **por categoria** (seção 12.1) |
| Acurácia da IA | Acurácia + recall/F1 dos Modelos 1 e 2 no conjunto de teste |
| Tempo médio de match | `aceite_ong − cadastro_lote` (e tempo total até a coleta) |
| Vulnerabilidades mitigadas | Achados Bandit/Trivy corrigidos por execução do pipeline |

### 12.1 Conversão kg → refeições (método híbrido)

Não existe um padrão brasileiro oficial de "kg doado → refeição". Por isso o método combina normas brasileiras, onde existem, com uma referência internacional:

| Categoria | Fórmula | Fonte |
|---|---|---|
| Preparado | `refeições = kg ÷ 0,420` | WRAP (Reino Unido): 420 g de alimento variado = 1 refeição, usado pela FareShare |
| Demais categorias | `refeições = kg × kcal_por_kg ÷ 700` | kcal/kg: **TACO/TBCA** (tabela brasileira de composição). 700 kcal = ponto médio da refeição principal do **PAT** (Portaria Interministerial nº 66/2006: 600–800 kcal) |

- O `kcal_por_kg` de cada categoria é a média de itens representantes escolhidos na TACO. Os itens e valores ficam documentados no gerador de dados.
- O resultado é conservador para itens de baixa densidade energética (hortifruti) e fiel para grãos e industrializados.
- Checagem de sanidade: a Feeding America (EUA/USDA) usa 1,2 lb (~544 g) por refeição.

**Referências:**
- WRAP / FareShare: https://wheresthefood.org.uk/appendix/appendix-1/
- Feeding America: https://www.hacap.org/download_file/view/115/244
- PAT, parâmetros nutricionais: https://www.guiatrabalhista.com.br/noticias/mudanca_refeicoes.htm
- TBCA: https://www.tbca.net.br/

### 12.2 Benchmark de mercado

- Tempo médio de match: a plataforma **Comida Invisível** divulga ~8 min em média para uma doação encontrar destino (https://consumidormoderno.com.br/comida-invisivel-desperdicio/). É a referência do KPI.

---

## 13. Pontos em aberto

- [x] Faixas de prioridade (5.1): validadas, com Preparado dividido por armazenamento
- [x] Validade efetiva calculada pelo sistema (4.2) + rota expressa (7.5)
- [x] Ajuste de peso > 50 kg (5.1): confirmado
- [x] ONG informa os turnos de refeição (6.4)
- [x] Validade mínima de Congelado: 24 h
- [x] PF não doa Padaria
- [x] Pesos do ranking de ONGs (6.1): confirmados
- [x] Fatores kg→refeição: método híbrido WRAP + TACO/PAT (12.1)
- [x] Retenção de dados: 12 meses (11)
