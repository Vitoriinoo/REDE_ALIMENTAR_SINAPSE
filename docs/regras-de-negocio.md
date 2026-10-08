# Rede Alimenta IA: Regras de Negócio

> **Status:** v2.0, decisões do grupo em 2026-10-05 sobre a v1.1 (2026-09-23).
> Este documento é a **fonte de verdade** do gerador de dados (`src/data`), dos modelos (`src/models`), da validação (`src/validacao`), da observabilidade (`src/observabilidade`) e da Matriz STRIDE (`docs/stride`).
> Requisitos de produto: [PRD](prd.md). Arquitetura: [SDD](sdd.md). Governança: [docs/governanca](governanca/).

### O que mudou na v2.0

| Tema | v1.1 | v2.0 | Seção |
|---|---|---|---|
| Pessoa física (CPF) | Doava Não perecível e Hortifruti | Doa **só Não perecível lacrado** na embalagem original | 4.1 |
| Questionário do lote | — | Perguntas obrigatórias que viram uma **Declaração de Doação** assinada e imutável | 4.5 |
| Validação de entrada | Só o texto livre passava por guardrail | **Tudo** que entra é validado antes de ser considerado (lista fechada, faixas, dígito verificador) | 4.6 |
| Verificação do CNPJ | Simulada | **Dígito verificador** (inclusive alfanumérico) + consulta à Receita (BrasilAPI) | 6.3 |
| Capacidades da ONG | Refrigeração | Cozinha, refrigeração, freezer, distribui cestas, veículo próprio, **janela de recebimento**, categorias aceitas | 6.4 |
| Ranking | Distância | **Tempo até a ONG poder receber**, complementaridade busca × entrega, bônus de pedido aberto | 6.1 |
| Pedidos da ONG | — | A ONG **pede alimentos** (mural + bônus no ranking) | 6.5 |
| Logs | Formato de exemplo | **Completo em cobertura, mínimo em conteúdo**, encadeado por HMAC, retenção 90 dias / 5 anos | 10.1 |
| Observabilidade | — | Alerta quando algo **sai do normal**, não só quando bate o teto | 10.2 |
| Controle da IA | Implícito | Desligamento por modelo, piso de segurança, inventário de agência | 10.3 |
| Feedback humano | — | Ciclo de **4 passos** (RLHF adaptado a classificadores) | 10.4 |

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
| Entrada não confiável | Tudo que entra (formulário, texto, resposta de API externa) é validado antes de ser considerado (4.6) |
| Observabilidade | O sistema compara o comportamento com o normal e avisa no desvio, antes do teto (10.2) |
| IA desligável | Cada modelo pode ser desligado sem parar o sistema: a regra no código assume (10.3) |

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
| **Doador PJ** | Restaurante, mercado, padaria, hortifruti, indústria (CNPJ) | Cadastrar lotes de **qualquer categoria**, acompanhar status, ver o mural de pedidos | Ver dados de outras doações, escolher a ONG |
| **Doador PF** | Pessoa física (CPF) | Cadastrar lotes **só de Não perecível lacrado** | Doar qualquer outra categoria |
| **ONG** | Associação/fundação com CNPJ **aprovada por admin** | Aceitar/recusar lotes, confirmar recebimento, **pedir alimentos** (6.5), declarar o que aceita (6.4), **solicitar** uso do caixa | Aprovar gasto do caixa, ver dados de outras ONGs |
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
| Hortifruti | Frutas, verduras, legumes | ✅ | ❌ | ❌ |
| Padaria | Pães, bolos | ✅ | ❌ | ❌ |
| Não perecível | Grãos, enlatados, industrializados lacrados | ✅ | ✅ **só lacrado** | ❌ |

> Base legal: a **Lei 14.016/2020** regula a doação de excedentes por estabelecimentos. Alimento preparado só vem de PJ, que responde sanitariamente.
> **v2.0: CPF só doa alimento não preparado, industrializado e lacrado** (ex.: saco de arroz, lata de óleo), **na embalagem original** e dentro da validade do rótulo. Hortifruti de PF saiu porque o produto in natura caseiro não tem rastreabilidade sanitária. A exigência de lacre é revalidada no questionário (4.5): embalagem aberta bloqueia o cadastro.

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
   > Histórico: a primeira versão usava zero-shot por NLI e ficou em 49% de acurácia e 3,3 s por texto. A troca para similaridade levou a 76% e 4,6 ms (ver `reports/avaliacao_nlp.json`). Com o dataset v2.0, a mesma comparação deu 75,3% em 4,4 ms contra 50% em 3,8 s.
4. **O doador confirma ou corrige.** A sugestão nunca é gravada sem confirmação.
5. A regra da seção 4.1 (PF × categoria) é revalidada **no código** depois da confirmação.

### 4.5 Questionário do lote e Declaração de Doação (v2.0)

Depois de confirmar categoria e armazenamento, o doador responde um **questionário obrigatório**. As respostas viram um **documento auditável**: o registro de **o que** foi disponibilizado, **por quem**, **quando** e **em que condições**.

**Perguntas**

| ID | Pergunta | Vale para | Efeito |
|---|---|---|---|
| Q1 | Origem do alimento (excedente de produção, excedente de estoque, sobra de evento, outro) | Todas | Informativo |
| Q2 | A embalagem ou o recipiente está íntegro (sem furo, estufamento, vazamento ou violação)? | Todas | **Não → bloqueia** |
| Q3 | Contém alergênicos? (glúten, crustáceos, ovos, peixes, amendoim, soja, leite/lactose, castanhas, nenhum, não sei) | Todas | Informativo: segue para a ONG |
| Q4 | Precisa ser cozido ou preparado antes de consumir? | Todas | Filtro de ONG: exige cozinha ou distribuição de cestas (6.4) |
| Q5 | Declaro que o alimento está dentro do prazo de validade e mantém integridade, segurança sanitária e propriedades nutricionais (Lei 14.016/2020, art. 1º) | Todas | **Sem aceite → bloqueia** |
| Q6 | O alimento ficou exposto ao consumidor (buffet, balcão de autosserviço, mesa)? | Preparado | **Sim → bloqueia** |
| Q7 | O rótulo com a validade está visível? | Refrigerado, Congelado | **Não → bloqueia** (a validade efetiva depende do rótulo, 4.2) |
| Q8 | O produto foi descongelado alguma vez? | Congelado | **Sim → bloqueia** (não pode ser recongelado) |
| Q9 | Está lacrado na embalagem original de fábrica? | Doador PF | **Não → bloqueia** (4.1) |
| Q10 | Foi selecionado (sem partes podres, mofo ou insetos)? | Hortifruti | **Não → bloqueia** |

> Por que o questionário fica no código e não na IA: são condições de **segurança alimentar** e de **responsabilidade legal**. A Lei 14.016/2020 (art. 3º) diz que o doador só responde civilmente se agir com dolo. Por isso a declaração explícita do doador é a evidência central.

**Declaração de Doação (documento auditável)**

| Aspecto | Regra |
|---|---|
| Conteúdo | ID e versão, lote, doador (pseudônimo e tipo), data e hora (UTC), versão das regras, categoria e armazenamento **confirmados** + a **sugestão da IA** (com a confiança), peso, validade efetiva e a base do cálculo, respostas Q1–Q10, resultado (ACEITA ou BLOQUEADA, com os motivos) e o texto da declaração legal |
| Integridade | JSON **canônico** (chaves ordenadas, UTF-8, sem espaços) → **SHA-256** → **assinatura RSA-PSS** (SHA-256, chave de 3072 bits) da plataforma (aula 3) |
| Imutabilidade | Gravação só de inclusão. Uma correção gera **nova versão** que aponta para o hash da anterior. Nada é sobrescrito nem apagado |
| Chaves | A chave privada fica fora do repositório (cofre de segredos/variável de ambiente). A chave pública é publicada para qualquer auditor verificar |
| Leitura humana | **PDF** gerado a partir do JSON, com o hash e a assinatura impressos. O documento oficial é o JSON assinado |
| Privacidade | Nenhum dado pessoal em claro: o doador aparece pelo pseudônimo (HMAC, seção 11) |
| Retenção | 5 anos, igual à trilha de auditoria (10.1) |

Uma declaração **BLOQUEADA também é guardada**. Ela prova que o sistema recusou o alimento, e por quê.

### 4.6 Validação de entrada (v2.0)

**Tudo que entra é dado não confiável até ser validado**: formulário, texto livre, arquivo, parâmetro de URL e também **resposta de serviço externo** (ex.: BrasilAPI).

| Camada | O que verifica | Onde |
|---|---|---|
| 1. Esquema | Tipo estrito, formato, faixa, lista fechada (enum); **campo desconhecido é rejeitado** | `src/validacao/esquemas.py` (Pydantic) |
| 2. Identidade | Dígito verificador de CPF/CNPJ, consulta à Receita (6.3) | `src/validacao/documentos.py`, `receita.py` |
| 3. Conteúdo | Guardrail do texto livre (4.4) | `src/seguranca/guardrails.py` |
| 4. Regra de negócio | PF × categoria, validade mínima, coerência entre datas, capacidade | `src/regras/` |
| 5. Banco | Restrições (CHECK, NOT NULL, FK) repetem as faixas: defesa em profundidade | Supabase (CP3) |

**Limites principais**

| Campo | Regra |
|---|---|
| Peso do lote | 0,5 a 2.000 kg. De 2.000 a 10.000 kg vai para **revisão do admin** antes do matching. Acima de 10.000 kg é rejeitado (erro de digitação) |
| Texto livre | Até 500 caracteres, depois do guardrail |
| Hora do preparo | Com fuso horário, nunca no futuro (tolerância de 5 min de relógio), no máximo 72 h atrás |
| Saída da refrigeração | Nunca no futuro (mesma tolerância), no máximo 24 h atrás |
| Validade do rótulo / informada | Com fuso, no máximo 2 anos à frente |
| CPF / CNPJ | Dígito verificador válido. CNPJ aceita o formato **alfanumérico** (IN RFB 2.229/2024, vigente desde jul/2026) |
| Coordenadas | Dentro da caixa geográfica do recorte (RMSP) |
| Capacidade da ONG | 1 a 10.000 kg/dia. Refrigerada ≤ total |
| Janela de recebimento | Abertura < fechamento, horas entre 0 e 24 |
| Pedido de ONG | kg ≤ capacidade diária; validade ≤ 7 dias; no máximo 3 pedidos abertos |

**Falha fechada:** se a validação de um serviço externo falhar (fora do ar, resposta fora do esquema), o cadastro fica **pendente de revisão manual**. Nunca é aprovado por omissão.
**Mensagem de erro:** o usuário recebe uma mensagem genérica que diz o campo e a regra, sem ecoar o valor recebido. O detalhe vai para o log operacional (10.1).

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

**Etapa 1: filtros obrigatórios (regra no código, nunca no score).** A ONG só entra no ranking se **todos** valerem:

| Filtro | Regra |
|---|---|
| Aprovada | Status `aprovada` (6.3) |
| Raio | Até 20 km do doador |
| Categoria aceita | A categoria está na lista que a ONG declarou (6.4) |
| Refrigeração | Item de cadeia fria **fora da rota expressa** exige refrigeração; **Congelado** em freezer exige freezer |
| Preparo | Lote que **requer preparo** (Q4) só vai para ONG com **cozinha** ou que **distribui cestas** (a família cozinha em casa) |
| Capacidade | Capacidade do dia restante ≥ peso do lote |
| Disponibilidade | O lote consegue **chegar dentro da janela de recebimento** antes do limite de consumo |
| Rota expressa | ONG serve refeição no mesmo turno e o trajeto ≤ 30 min (7.5) |

**Etapa 2: score de prioridade entre as elegíveis.**

```
score = 0,30·acesso + 0,15·capacidade + 0,30·vulnerabilidade + 0,10·turno
      + acesso · (0,15·complementaridade + 0,10·pedido_aberto)
```

| Componente | Cálculo |
|---|---|
| **acesso** (v2.0, substitui a distância) | `1 − min((tempo_até_receber − 30 min) / 60 min, 1)`, com `tempo_até_receber = max(30 min + trajeto, espera até a janela de recebimento abrir)`. Os **30 min** são a antecedência operacional (mediana de match + coleta). Sem ela, o sistema acharia que o lote chega "agora + trajeto" e escolheria ONGs que fecham antes da entrega. Ela é igual para todas as ONGs, então só a parte variável pontua. **60 min** ≈ trajeto do raio de 20 km fora do pico |
| capacidade | Fração livre da capacidade do dia |
| vulnerabilidade | Grupo IPVS do **setor** da ONG, de 1–6 normalizado para 0–1 |
| turno | 1 se a ONG serve refeição antes do limite de consumo, senão 0,5 |
| **complementaridade** (v2.0) | 1 = complementar · 0,5 = nenhum dos dois tem transporte · 0 = redundante (6.6) |
| **pedido aberto** (v2.0) | 1 se a ONG tem pedido aberto da mesma categoria (6.5) |

> **Por que complementaridade e pedido são multiplicados pelo acesso:** eles **desempatam entre ONGs acessíveis**, mas não puxam o lote para longe. Na calibração com o dataset simulado, somar os dois "por inteiro" levava o lote a ONGs com veículo mais distantes (o carro da ONG não é refrigerado). Isso aumentava a quebra de cadeia fria e o descarte em **1 p.p.** Multiplicados pelo acesso, o custo cai para **~0,2 p.p.**, e a maioria dos matches continua complementar (ver [PRD](prd.md), métricas).

Os pesos ficam versionados no código (`src/regras/logistica.py`) e são auditáveis.

> Decisão de impacto social: a vulnerabilidade continua com o mesmo peso do acesso. Às vezes a comida vai um pouco mais longe para chegar a quem mais precisa.
> Por que **tempo até receber** e não distância: uma ONG a 2 km que só abre amanhã às 9 h é pior para uma marmita do que outra a 8 km aberta agora. A distância sozinha esconde isso.

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

A verificação vale para **todo CNPJ** (ONG e doador PJ) e tem três passos:

| Passo | O que prova | Como |
|---|---|---|
| 1. Dígito verificador | Que o número **pode** existir (formato) | Cálculo módulo 11 no código. Aceita o **CNPJ alfanumérico** (IN RFB 2.229/2024): cada caractere vale `código ASCII − 48` |
| 2. Consulta à Receita | Que o CNPJ **existe e está ativo** | BrasilAPI (gratuita), com cache de 24 h e timeout curto. A resposta é validada por esquema (4.6) |
| 3. Aprovação humana | Que a entidade é quem diz ser | Admin aprova (ONG) |

- **ONG:** situação **ATIVA** e natureza jurídica de entidade sem fins lucrativos: 306-9 Fundação Privada, 320-4 Fundação/Associação estrangeira no Brasil, 322-0 Organização Religiosa, 330-1 Organização Social, 399-9 Associação Privada.
- **Doador PJ:** situação **ATIVA**. Se o CNAE principal não for do ramo de alimentos (agricultura, indústria de alimentos, atacado/varejo de alimentos, alimentação), o cadastro **não é bloqueado** mas vai para **revisão do admin** (ex.: refeitório de uma empresa de outro ramo).
- Passo 1 falhou: rejeita na hora. Passo 2 indisponível: fica **pendente** (falha fechada, 4.6).
- **Aprovação manual por Admin** antes de a ONG receber qualquer lote.
- Só ONG aprovada pode solicitar uso do caixa solidário.

> O dígito verificador **não prova** que o CNPJ é verdadeiro. Ele só pega erro de digitação e número inventado ao acaso. Quem prova existência é a consulta à Receita, e quem prova legitimidade é o admin.

### 6.4 Cadastro operacional da ONG

Para entrar no matching, a ONG informa:
- **Capacidade diária** (kg) e se possui **refrigeração** (e capacidade refrigerada) e **freezer**;
- **Cozinha:** tem espaço para preparar alimentos? Sem cozinha, a ONG **não recebe alimento que requer preparo** (Q4), exceto se **distribui cestas** às famílias;
- **Distribui cestas:** entrega alimento para preparo em casa (cesta básica, sacolão);
- **Janela de recebimento** (v2.0): horário em que recebe entregas (ex.: 8 h–18 h). Fora da janela, o lote espera, e essa espera entra no ranking (6.1);
- **Veículo próprio** (v2.0): pode buscar o lote no doador (6.6);
- **Turnos em que serve refeição** (`café` · `almoço` · `jantar` · `noturno`). O turno `noturno` (20 h–23 h) é o dos coletivos que distribuem refeições à noite, por exemplo à população em situação de rua. É obrigatório para receber lotes da rota expressa (7.5): o lote só vai para uma ONG cujo próximo turno comece antes de a validade efetiva vencer. ONG com turno noturno tem a janela de recebimento estendida até 23 h;
- **Categorias aceitas:** a ONG **filtra** o que aceita. A lista não pode incluir algo que a estrutura não comporta: sem refrigeração não há como aceitar Refrigerado/Congelado, sem freezer não há como aceitar Congelado;
- **Região atendida.**

### 6.5 Pedidos da ONG (v2.0)

A ONG pode **pedir** alimentos, e não só esperar ofertas.

| Regra | Valor |
|---|---|
| Conteúdo | Categoria, kg desejados, validade do pedido, observação curta (passa pelo guardrail) |
| Limites | kg ≤ capacidade diária · validade ≤ 7 dias · no máximo **3 pedidos abertos** por ONG |
| Mural | Doadores veem os pedidos **agregados por região** (categoria e kg), nunca o endereço da ONG |
| Ranking | Pedido aberto da mesma categoria do lote = **+0,10** no score (6.1) |
| Atendimento | Cada entrega confirmada abate os kg do pedido. Atingido o total ou vencido o prazo, o pedido fecha |
| Notificação | Só para doadores que **ativarem** essa opção, no máximo 1 aviso por dia por doador |
| Abuso | ONG cujos pedidos ficam muito acima do que ela recebe/confirma (fora da linha de base, 10.2) gera alerta ao admin |

### 6.6 Complementaridade busca × entrega (v2.0)

Doador e ONG declaram se têm transporte: o doador **pode entregar**, a ONG **pode buscar**. Para não desperdiçar a capacidade logística da rede:

| Doador entrega? | ONG busca? | Situação | Complementaridade |
|:-:|:-:|---|:-:|
| Sim | Não | **Complementar:** o doador leva | 1 |
| Não | Sim | **Complementar:** a ONG busca | 1 |
| Não | Não | Depende da cascata de transporte (7.2) | 0,5 |
| Sim | Sim | **Redundante:** gasta o veículo da ONG que outro doador sem transporte precisaria | 0 |

**É preferência forte, não proibição.** Se a única ONG viável for "redundante", o lote vai para ela mesmo assim: perder a comida é pior do que usar mal um veículo.

---

## 7. Transporte

### 7.1 Modalidades

| Modalidade | Custo | Frota simulada | Observação |
|---|---|---|---|
| ONG retira | Grátis | ONGs com **veículo próprio** (6.4) | Só se a ONG declarou que pode buscar |
| Voluntário retira | Grátis | 70 voluntários | Disponibilidade esporádica |
| Doador entrega | Grátis | Doadores que **podem entregar** (6.6) | Até a ONG ou até um hub |
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

**Features (sem dados pessoais):** categoria, armazenamento, rota expressa, prioridade prevista, horas até vencer, peso, segmento/tipo de doador, **doador tem refrigeração**, região, hora do dia, dia da semana, mês, feriado, nº de ONGs compatíveis num raio de 10 km, distância da ONG mais bem ranqueada, nº de transportadores ativos no raio, disponibilidade de veículo refrigerado. **v2.0:** minutos até a ONG do topo poder receber, doador pode entregar, requer preparo. (O mês fica de fora: com split temporal, os meses do teste nunca aparecem no treino.)

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

## 10. Rastreabilidade, observabilidade e controle da IA

### 10.1 Logs: completos em cobertura, mínimos em conteúdo (v2.0)

> A Aula 6 lista **"Logs completos"** como **risco**: guardar prompts inteiros com dados pessoais. O controle C5 da mesma aula diz *"minimizar, mascarar e definir retenção"*. Por isso **tudo é registrado**, mas **nada sensível vai em claro**.

**O que gera registro (cobertura completa)**

| Tipo | Exemplos | Trilha |
|---|---|---|
| Acesso | Toda requisição: rota, método, status, latência, usuário (pseudônimo), IP (HMAC) | Operacional |
| Autenticação | Login, falha de login, logout, troca de senha, MFA | Auditoria |
| Validação | Entrada rejeitada (campo e regra, **nunca o valor**), bloqueio do guardrail (motivo, tamanho e hash do texto) | Operacional |
| Decisão de negócio | Cadastro, bloqueio, declaração emitida, oferta, aceite, recusa, escalada, transporte, entrega, inspeção | Auditoria |
| Chamada de IA | Modelo, versão, hash das entradas, saída, confiança, latência, se houve fallback para a regra | Auditoria |
| Dinheiro | Pedido, aprovação e negação do caixa, valores e aprovador | Auditoria |
| Administração | Aprovação de ONG, mudança de parâmetro, desligamento de modelo, liberação de freio | Auditoria |
| Observabilidade | Alertas emitidos e reconhecidos (10.2) | Operacional |

**Formato:** uma linha JSON por evento, com `evento_id`, `ts` (UTC), `correlacao_id` (liga a requisição a todas as decisões que ela gerou), `componente`, `ator` (pseudônimo), `papel`, `acao`, `recurso`, `resultado` (`sucesso`, `negado`, `erro`), `detalhes`, `versao_regras`.

```json
{"acao":"PREDICAO_PRIORIDADE","ator":"doador:7c1e…","componente":"ia.prioridade","correlacao_id":"5b0d…",
 "detalhes":{"modelo":"prioridade-v2","saida":"CRITICA","confianca":0.91,"fallback":false},
 "evento_id":"…","papel":"doador","recurso":"lote:L-000123","resultado":"sucesso",
 "ts":"2026-10-05T19:42:00Z","versao_regras":"2.0","hash_anterior":"…","hash":"…"}
```

**Minimização (aplicada no código, não na boa vontade de quem escreve o log):**
- Chaves proibidas (`cpf`, `cnpj`, `nome`, `email`, `telefone`, `endereco`, `texto`, `senha`, `token`…) são **removidas** antes de gravar.
- Valores com cara de CPF, CNPJ, e-mail ou telefone são **mascarados**.
- O texto livre do doador **nunca** vai para o log: só o hash, o tamanho e os motivos do guardrail.

**Integridade da trilha de auditoria:** cada registro carrega `hash_anterior` e `hash = HMAC-SHA256(chave, hash_anterior + registro)`. Alterar, apagar ou reordenar qualquer linha **quebra a cadeia** e a verificação aponta onde. Com HMAC (e não SHA-256 simples), quem tem acesso de escrita ao arquivo mas não tem a chave **não consegue recalcular** a cadeia.

**Retenção**

| Trilha | Prazo | Justificativa |
|---|---|---|
| Operacional (acesso, validação, alertas) | **90 dias** | Investigação de incidente e linha de base da observabilidade |
| Auditoria (decisões, dinheiro, administração, declarações) | **5 anos** | Prazo do CDC (art. 27) para reparação de danos, por analogia. Cobre questionamentos sanitários e do caixa |

### 10.2 Observabilidade: alertar no desvio, não só no teto (v2.0)

O sistema não espera algo quebrar. Ele aprende o **comportamento normal** de cada sinal e avisa quando o valor **sai do normal**, mesmo que ainda esteja longe de qualquer teto.

**Linha de base:** para cada sinal, mediana e MAD (desvio absoluto mediano) do histórico, **separados por faixa de hora e por dia útil/fim de semana**, porque as doações têm picos naturais (um sábado à noite agitado não é anomalia). Desvio robusto: `z = 0,6745 · (valor − mediana) / MAD`. Mediana e MAD não são distorcidos pelas próprias anomalias, ao contrário de média e desvio-padrão.

| Nível | Quando | Ação |
|---|---|---|
| **Atenção** | `z ≥ 3,5` (critério de Iglewicz–Hoaglin) **ou** 70% de um teto | Registro + painel |
| **Alerta** | `z ≥ 7` **ou** 90% de um teto | Painel em destaque. Se for sinal de **segurança**: **freio automático** |
| **Crítico** | Bateu o teto / regra violada | O próprio teto bloqueia (regra no código) + alerta |

Sem histórico mínimo (8 observações na faixa), o sinal fica em **aquecimento** e só o teto vale.

**Sinais monitorados**

| Sinal | Chave | Tipo |
|---|---|---|
| Requisições por minuto | usuário e IP | Segurança |
| Falhas de login (15 min) | IP e conta | Segurança |
| Bloqueios do guardrail (1 h) | usuário e global | Segurança |
| Cadastros por dia | doador (comparado com o **próprio** histórico) | Negócio |
| Peso do lote (em **escala log**: o desvio é medido em "vezes o normal") | doador | Negócio |
| Recusas por dia | ONG | Negócio |
| Pedidos × recebimentos | ONG | Negócio |
| Gasto do caixa no dia | ONG (fração do teto) | Negócio |
| Drift das entradas e das predições | modelo (PSI: < 0,1 estável · 0,1–0,25 atenção · > 0,25 alerta) | IA |
| Latência p95 e taxa de erro (5 min) | rota | Operação |

**Resultado no ano simulado** (`python -m src.observabilidade.demo` → `reports/observabilidade_demo.json`):

| Pergunta | Resultado |
|---|---|
| Alarmes falsos em dados normais (fadiga) | Cadastros/dia: 1 atenção em 109.500 medições · Recusas/dia: 2 alertas em 7.795 · Peso: 1 alerta e 96 atenções em 25.045 lotes |
| Anomalias injetadas | 25 lotes num dia → **ALERTA** · rajada de 200 req/min → **ALERTA** na 37ª requisição, com **freio aplicado** · caixa a 92% do teto → **ALERTA** · lote 50× o normal → **ATENÇÃO** |
| Limite conhecido | Lote **10×** o normal do doador **não** dispara: o peso simulado varia muito, e 10× ainda está dentro da variação natural. A regra fixa de revisão humana acima de 2 t cobre os casos extremos |

> Por que o peso é medido em escala log: peso é uma grandeza **multiplicativa**. Na escala linear, a cauda longa gerava alarme em 6% dos lotes normais (1.528 em um ano). Em log, caiu para 0,4% (97).

**Freio automático (só para sinais de segurança, nível Alerta):** limite de requisições reduzido para a chave por **15 minutos**. É **reversível** (expira sozinho ou o admin libera) e fica registrado. Um humano revisa todo freio. Sinais de **negócio** nunca bloqueiam sozinhos: só avisam, porque um doador que doa muito mais num dia pode ser só um bom dia.

### 10.3 Controle da IA (v2.0)

A IA **recomenda**, nunca executa. O inventário completo (o que cada modelo lê, o que pode alterar, quem confirma, o que acontece se errar ou for atacado) está em [docs/governanca/analise-agencia-ia.md](governanca/analise-agencia-ia.md).

| Controle | Regra |
|---|---|
| Desligamento por modelo | Cada modelo (NLP, M1, M2) pode ser desligado sem parar o sistema. Desligado, a regra assume: NLP → o doador escolhe a categoria sozinho; M1 → `prioridade_por_regra`; M2 → heurística v0 |
| Piso de segurança do M1 | Se a regra diz **CRÍTICA**, a prioridade final é CRÍTICA, mesmo que o modelo diga outra coisa. O modelo pode **subir** a urgência, nunca baixar a de um caso crítico (o erro de baixar custa comida perdida) |
| Saída validada | A saída de cada modelo é conferida contra a lista fechada de rótulos e a faixa [0, 1] de probabilidade. Fora disso, a regra assume e o evento vai para o log |
| Integridade do artefato | O modelo só é carregado se o SHA-256 bater com os metadados |
| Toda chamada é logada | Modelo, versão, entradas (hash), saída, confiança, latência, fallback (10.1) |

### 10.4 Ciclo de feedback humano (RLHF adaptado, v2.0)

O RLHF clássico (pré-treino → preferências humanas → modelo de recompensa → otimização por PPO) foi feito para LLM, e este sistema usa classificadores. A ideia central é a mesma: **o humano corrige a IA e a correção melhora o próximo modelo**. Adaptado em 4 passos:

| Passo | O que acontece | Controle |
|---|---|---|
| 1. A IA sugere | NLP sugere categoria, M1 sugere prioridade, M2 estima risco | Toda sugestão é logada com a versão do modelo |
| 2. O humano corrige | Doador corrige a categoria, admin/triador corrige a prioridade, ONG recusa na inspeção (rótulo de qualidade) | A correção é um evento de auditoria |
| 3. O feedback é validado | Só de contas **verificadas**; no máximo **20 correções por ator por dia**; nenhum ator responde por mais de **2% dos rótulos novos**; ator com taxa de correção fora da linha de base vai para **quarentena** e revisão | Defesa contra **envenenamento de dados** (OWASP LLM04, MITRE ATLAS AML.T0020) |
| 4. Retreino com portão | O modelo candidato só é promovido se **não piorar** (tolerância de 0,5 p.p.) no conjunto de teste fixo (que nunca recebe feedback), mantiver as metas (recall CRÍTICA ≥ 90%, recall descarte ≥ 85%) e um **humano diferente de quem treinou** aprovar | Versão anterior guardada para **rollback** |

**Demonstração com o NLP real** (`python -m src.models.demo_feedback` → `reports/feedback_demo.json`). Foram 5.749 feedbacks: os doadores honestos do período de validação, 80 "correções" de um atacante (marmita → não perecível) e 30 de uma conta não verificada.

| Candidato | Acurácia (teste fixo) | Preparado | Portão |
|---|---|---|---|
| Modelo atual | 75,3% | 68% | — |
| Validado, **todos** os rótulos humanos (confirmações + correções) | **85,3%** | 72% | ✅ promovido |
| Validado, **só as correções** | 66,0% | 54% | ❌ barrado (piorou) |
| **Sem** a validação (com o veneno) | 86,3% | 72% | ⚠️ passaria |

O que a demonstração mostra:
1. **O passo 3 é a defesa central.** O atacante foi para a quarentena com 0 feedbacks aceitos, e a conta não verificada foi barrada. Sem essa validação, o veneno, diluído em 5,7 mil rótulos, **não mexe na métrica** e **passaria no portão**. Um envenenamento discreto não aparece na acurácia: por isso a origem do dado é validada antes.
2. **O portão protege contra retreino ingênuo.** Treinar só com as correções (os textos difíceis) piorou o modelo, e o portão barrou.
3. **Custo da quarentena:** 1 doador honesto que corrigia muito (60% vs. mediana de 24%) também foi para a quarentena. Ela gera **revisão humana**, não punição.
4. **Limite:** a quarentena compara o ator com os pares e só funciona quando eles têm histórico (≥ 10 feedbacks). Com pouco feedback, só a cota por ator segura o atacante.
5. **Ressalva:** o teste vem do mesmo gerador de frases do dataset simulado, então o ganho de 75% → 85% é otimista. O conjunto independente do grupo é a verificação real.

---

## 11. Privacidade (LGPD): regras de base

- **CPF/CNPJ** são armazenados só como **HMAC-SHA256 com chave secreta** (nunca em claro). A chave fica num cofre de segredos, fora do código e do banco.
  > Por que não SHA-256 com salt: existem só ~10⁹ CPFs válidos. Um hash sem segredo é revertido por **força bruta** em minutos (aula 3). Com HMAC, sem a chave o hash não serve para nada.
- **Endereço de PF:** só o centroide do bairro até o aceite do match.
- **Modelos de IA** nunca recebem nome, CPF, telefone ou endereço exato.
- **Retenção:** dados de contato apagados/anonimizados 12 meses após a última atividade. Métricas agregadas são mantidas. Logs: 90 dias (operacional) e 5 anos (auditoria e declarações), sempre sem dado pessoal em claro (10.1).
- **Governança:** inventário de dados (registro de tratamento, LGPD art. 37), classificação por campo, bases legais, RIPD e linhagem ficam em [docs/governanca](governanca/). A classificação é **verificada por teste**: uma coluna nova sem classificação quebra o pipeline.

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

**v2.0: decididos pelo grupo em 2026-10-05**
- [x] PF só doa Não perecível lacrado (4.1)
- [x] Logs completos em cobertura e mínimos em conteúdo, retenção 90 dias / 5 anos (10.1)
- [x] Observabilidade por linha de base estatística, freio automático só para segurança (10.2)
- [x] Questionário + Declaração assinada (RSA-PSS) e imutável (4.5)
- [x] CNPJ: dígito verificador (com alfanumérico) + BrasilAPI (6.3)
- [x] Pedidos de ONG, filtro por cozinha, tempo até receber, complementaridade como preferência (6.1, 6.4–6.6)
- [x] Feedback humano em 4 passos (10.4)

**v2.0: valores propostos na implementação, para o grupo revisar**
- [ ] Pesos do score v2 (6.1): acesso 0,30 · capacidade 0,15 · vulnerabilidade 0,30 · turno 0,10 · complementaridade 0,15 · pedido +0,10
- [ ] Perguntas Q7, Q8 e Q10 do questionário como bloqueio (4.5)
- [ ] Faixa de peso que vai para revisão do admin: 2.000–10.000 kg (4.6)
- [ ] Limites do feedback: 20 correções/ator/dia e 2% dos rótulos novos (10.4)
