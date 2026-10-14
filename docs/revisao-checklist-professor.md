# Revisão crítica: checklist do professor × projeto

## Atualização v2.1 (2026-10-14): situação final

| # | Item | 08/10 | 14/10 | O que mudou |
|---|---|:-:|:-:|---|
| 1 | CPF não doa preparado | ✅ | ✅ | Na API, o tipo do doador vem da **conta autenticada**; campo extra no corpo → 422 (teste) |
| 2 | ONG pede alimentos | 🟡 | ✅ | Ciclo de vida do pedido desenhado no SDD §4.4; observação passa pelo guardrail |
| 3 | Filtro de recebimento | ✅ | ✅ | — |
| 4 | Distância + disponibilidade mútua | 🟡 | ✅ | Janela do doador + "disponível até" do lote entram em `tempo_ate_receber` como restrição dura |
| 5 | Bloqueio "só busca" × "só entrega" | ❌ | ✅ | Capacidade ≠ restrição; impasse **bloqueado** (hub como ponto de encontro); redundante proibido com alternativa (regras 6.6, D9) |
| 6 | DV do CNPJ | ✅ | ✅ | — |
| 7 | Validação de TUDO | 🟡 | ✅ | API existe; teste percorre todas as rotas e falha se alguma receber corpo sem esquema estrito; toda rota de negócio exige autenticação |
| 8 | IA isolada | 🟡 | ✅ | Container `inferencia` em rede interna sem saída, sem segredos, só leitura (D10); no Space público, risco residual documentado (D12) |
| 9 | GRC no SDD/PRD | 🟡 | ✅ | SDD §6 GRC + PRD RNF-10 Conformidade |
| 10 | Declaração auditável no banco | 🟡 | ✅ | `rede.declaracoes` só de inclusão (REVOKE + gatilho que barra até o dono), testada num PostgreSQL real |
| 11 | Logs completos | ✅ | ✅ | Login, aceite, entrega e interruptores da IA agora também são logados pela API |
| 12 | Observabilidade por anomalia | ✅ | ✅ | Freio integrado como middleware da API |
| 13 | RLHF em 4 passos | ✅ | ✅ | Tabela de mapeamento com o RLHF clássico (regras 10.4) |
| 14 | SDD/PRD + `NUMERIC` | ❌ | ✅ | `db/schema.sql` com NUMERIC em todo número, UUID, RLS; teste barra INTEGER/FLOAT; `Decimal` no caixa (D11) |

**Placar final: 14 ✅.** O histórico de 08/10 está abaixo, preservado.

---

## Revisão de 08/10 (v2.0)

> 2026-10-08 · conferido no código (`src/`), nos docs (`prd.md`, `sdd.md`, `regras-de-negocio.md`, `governanca/`) e na suíte de testes (**181 passando**).
> Legenda: ✅ atende · 🟡 atende em parte · ❌ não atende / diverge.

## Resumo

| # | Item | Veredito | Em uma frase |
|---|---|:-:|---|
| 1 | CPF não doa preparado | ✅ | Regra no código e testada, e mais restrita que o pedido (PF só doa não perecível lacrado) |
| 2 | ONG pede alimentos | 🟡 | Regra e limites prontos; falta o **fluxo** desenhado no SDD |
| 3 | Filtro de recebimento da ONG | ✅ | Filtro rígido por cozinha, refrigeração e freezer, com o motivo logado |
| 4 | Distância + disponibilidade mútua | 🟡 | Distância e janela da ONG entram; a disponibilidade do **doador** não é modelada |
| 5 | Bloqueio "só busca" × "só entrega" | ❌ | O projeto decidiu **preferência, não proibição**, e o modelo de dados nem consegue representar o "SÓ" |
| 6 | DV do CNPJ | ✅ | Módulo 11 real, incluindo CNPJ alfanumérico, + BrasilAPI + admin |
| 7 | Validação de TUDO | 🟡 | A camada de esquemas é forte, mas ainda não existe a API que obrigaria tudo a passar por ela |
| 8 | IA isolada | 🟡 | Isolada no desenho lógico (`ControleIA`); na infraestrutura, ainda não |
| 9 | GRC no SDD/PRD | 🟡 | O conteúdo existe em `docs/governanca/`, mas PRD e SDD não o tratam como GRC |
| 10 | Declaração auditável no banco | 🟡 | Assinada, imutável e versionada, mas gravada em **arquivo**, não no banco |
| 11 | Logs completos | ✅ | Duas trilhas, cadeia HMAC e minimização; a cobertura só vale para os módulos que já existem |
| 12 | Observabilidade por anomalia | ✅ | Linha de base mediana/MAD por hora×dia, 3 níveis, freio e PSI |
| 13 | RLHF em 4 passos | ✅ | 4 passos documentados e demonstrados; falta mapear com o RLHF clássico |
| 14 | SDD/PRD + `NUMERIC` | ❌ | Não há nenhum esquema relacional (DDL), então a restrição `NUMERIC` não foi cumprida |

**Placar:** 6 ✅ · 6 🟡 · 2 ❌. Os dois ❌ são os riscos de nota: o **item 5** porque contradiz uma regra explícita do professor, e o **item 14** porque é um artefato que falta por completo.

---

## Regras de negócio e lógica

### 1. Regra de doadores ✅
- **Evidência:** `src/regras/logistica.py::pode_doar` (`CATEGORIAS_PF = {NAO_PERECIVEL}`). `questionario.avaliar` bloqueia com `CATEGORIA_NAO_PERMITIDA_PARA_PF` e ainda exige o lacre (Q9). O CNPJ pode doar tudo. Testado em `test_regras.py` e `test_questionario.py`.
- **Ressalva 1:** o projeto é **mais restrito** que o checklist. O professor fala em "não preparados" e cita arroz como exemplo; o projeto também barra hortifruti e padaria para PF. Isso é defensável (falta rastreio sanitário de quem doa como PF), mas é uma divergência, e vocês precisam ter o argumento pronto.
- **Ressalva 2:** `CadastroLote` não traz `tipo_doador`. Na API, o tipo **precisa vir da conta autenticada**, nunca do corpo da requisição. Se vier do corpo, a regra é burlada mandando `"tipo": "PJ"`. Vale escrever isso no SDD §4.1.

### 2. Solicitação por ONGs 🟡
- **Existe:** a regra 6.5 (mural agregado por região, limite de 3 pedidos abertos, validade de até 7 dias, bônus no ranking, alerta de abuso), `validar_pedido`, o esquema `PedidoOng` e a simulação (`pedidos.csv` com 1.420 pedidos).
- **Falta:** o checklist pede o fluxo "documentado **e projetado**". O SDD tem diagrama do cadastro de lote (4.1) e do matching (4.2), mas **nenhum do ciclo de vida do pedido** (abrir → mural → notificação → abatimento → fechar/vencer). No PRD, o RF-10 está como "API no CP3".
- **Ação:** acrescentar um SDD §4.x com um diagrama de estados do pedido.
- **Observação:** a regra 6.5 diz que a observação do pedido "passa pelo guardrail", mas `PedidoOng.observacao` só passa por `_sem_controle`. Ver o item 7.

### 3. Filtro de recebimento ✅
- **Evidência:** `motivo_incompatibilidade` combina `categorias_aceitas`, refrigeração, freezer e `requer_preparo`, que exige cozinha **ou** `distribui_cestas`. O esquema `CadastroOng` impede a ONG de declarar uma categoria que a estrutura dela não comporta. O motivo da exclusão vai para o log.
- **Pergunta para vocês:** uma ONG que distribui cestas e não tem cozinha **passa** no filtro com alimento cru. A premissa é que a família cozinha em casa. O professor vai concordar com isso? Também não há filtro por alergênico nem por subtipo (por exemplo, "não aceito carne crua"). A granularidade parou na categoria.

### 4. Matchmaking logístico e geográfico 🟡
- **Distância:** atende. Raio de 20 km, score de acesso e `tempo_ate_receber = max(antecedência + trajeto, espera até a janela abrir)`.
- **Disponibilidade "mútua":** atende só **do lado da ONG**. O doador não tem janela de disponibilidade (`CadastroDoador` não tem horário). O sistema assume que o lote está disponível a partir do cadastro e até a validade. Um restaurante que fecha às 23h e cadastrou às 22h50 vai gerar match para uma coleta que não acontece.
- **Ação:** acrescentar "disponível até" ao lote, ou uma janela ao doador, e entrar com isso em `tempo_ate_receber` como restrição dura.

### 5. Regra de transporte ❌ (o ponto mais importante)
- **O que o checklist pede:** o algoritmo deve **impedir** o match entre uma ONG que *só* busca e um doador que *só* entrega (e vice-versa).
- **O que o projeto faz:** regra 6.6 + `complementaridade()`. A combinação "doador entrega e ONG busca" é **redundante**, vale 0 no score, mas **é permitida**: "é preferência forte, não proibição". Essa decisão foi tomada em 05/10 e está registrada.
- **Problema maior que a divergência:** `pode_entregar` e `pode_buscar` representam **capacidade** ("tem veículo"), não **restrição** ("só aceito assim"). O "SÓ" do professor não é representável no modelo de dados atual. Duas leituras possíveis:
  - **Leitura A (impasse):** a ONG só busca (não recebe no local) e o doador só entrega (ninguém pode coletar com ele). Ninguém fica parado esperando o outro, então o match é **impossível de executar**, não só ineficiente. Nesse caso, permitir o match é um **bug**, não uma escolha de calibração.
  - **Leitura B (desperdício):** os dois têm veículo, e o professor quer proibir para não gastar dois veículos. É o caso "redundante" de vocês, em que a decisão de não proibir pode ser defendida (perder a comida é pior), mas contradiz o checklist.
- **Saída sugerida para levar ao grupo:** separar capacidade de restrição (`doador.aceita_coleta`, `ong.aceita_receber_entrega`). O impasse vira filtro rígido em `motivo_incompatibilidade`, a menos que exista um **hub** (7.4) que sirva de ponto de encontro (o doador leva ao hub e a ONG busca no hub). Isso fecha a leitura A sem abrir mão do argumento da leitura B.
- **Pergunta para decidir antes de codar:** qual das duas leituras o professor quis dizer? Se não der para perguntar a ele, a opção segura é implementar o bloqueio da leitura A e manter a preferência da leitura B, documentando as duas.

---

## Segurança, governança e dados

### 6. Cálculo do CNPJ ✅
- **Evidência:** `src/validacao/documentos.py` tem o módulo 11 real, com os pesos 5..2/9..2 e 6..2/9..2, suporte ao CNPJ alfanumérico (IN RFB 2.229/2024, `ord(c) - 48`) e rejeição de repetidos (`len(set(c)) == 1`). `receita.py` consulta a BrasilAPI (situação ativa, natureza jurídica sem fins lucrativos, CNAE de alimentos) com falha fechada, e o admin aprova por último.
- **Ressalva para a apresentação:** sozinho, o DV **não impede cadastro falso**. Um CNPJ gerado por qualquer site de "gerador de CNPJ" passa no DV. Quem barra o falso é a consulta à Receita (que nos testes está mockada) e o admin. Falem isso antes que o professor pergunte.

### 7. Validação de entrada (TUDO) 🟡
- **Forte:** Pydantic `strict` + `extra="forbid"` + `frozen`. Datas exigem fuso, NaN e infinito são rejeitados, há caixa geográfica, caracteres invisíveis e de controle são barrados, o DV é checado no esquema e a resposta da BrasilAPI também é validada por esquema.
- **Por que ainda não é "TUDO":**
  1. **Não existe API.** Os esquemas são a camada 1 de algo que ainda não tem porta de entrada. Hoje não dá para provar que *todo* endpoint usa um esquema.
  2. `PedidoOng.observacao` e `RespostaOferta` não passam pelo guardrail, apesar de a regra 6.5 dizer que passam.
  3. Path/query params, cabeçalhos, tokens e upload ainda não foram desenhados.
  4. O guardrail v2 acerta 4/10 no conjunto B reservado: o risco residual está documentado, mas existe.
- **Ação (CP3):** um teste que percorra `app.routes` do FastAPI e falhe se alguma rota receber `dict`/`Any` em vez de um esquema `Entrada`. É isso que transforma "TUDO" de promessa em evidência.

### 8. Restrição da IA 🟡
- **Lógica (✅):** a IA não tem agência. `ControleIA` só devolve `Recomendacao`, e cada modelo tem interruptor. Há piso de segurança no M1, o artefato é verificado por SHA-256 antes do `joblib.load`, os modelos HF ficam fixados por commit e só em safetensors, toda chamada é logada e há uma análise 5C em `governanca/analise-agencia-ia.md`.
- **Infraestrutura (🟡):** o modelo roda **no mesmo processo** da API, com as mesmas permissões e acesso aos mesmos segredos. Se o professor entende "isolado na arquitetura" como fronteira física, ainda não existe.
- **Pergunta para vocês:** vale usar o CP2 (Docker/Compose) para pôr a inferência num container próprio, sem rede de saída, sem segredos e só leitura? Seria o argumento concreto para o item 8. Lembrete: injeção de prompt é um risco baixo aqui, porque o NLP é um classificador por embeddings, não um LLM. Digam isso explicitamente, senão parece que ignoraram o risco.

### 9. GRC e governança de dados 🟡
- **Existe:** `governanca/` com política de IA, RACI, matriz de controles ISO 27001/42001/CSF/OWASP, inventário (LGPD art. 37), RIPD e análise de agência, além do catálogo de dados verificado por teste e de 15 checagens de qualidade.
- **Falta:** a palavra "GRC" aparece **0 vezes** no PRD e no SDD. O checklist pergunta especificamente se "o SDD e o PRD contemplam". O SDD §6 cita "Governança" como camada, mas sem Risco e sem Compliance como pilares.
- **Ação:** uma seção "GRC" no SDD com 3 linhas (Governança → política e RACI; Risco → STRIDE + P×I e registro de riscos; Compliance → LGPD, Lei 14.016, CDC art. 27, ISO) e links para `governanca/`. No PRD, um RNF "Conformidade". É meia hora de trabalho para converter 🟡 em ✅.

### 10. Documento auditável de doação 🟡
- **Atende:** JSON canônico, SHA-256, assinatura RSA-PSS 3072, PDF, versões encadeadas por hash, gravação em modo `"x"` (só inclusão), quem/quando/o quê com o doador pseudonimizado e bloqueios por exposição ao consumidor e embalagem violada. Testado em `test_declaracao.py`.
- **Não atende:** o checklist diz "**salvo no banco de dados**", e hoje o documento vai para `var/declaracoes/*.json`. Além disso, o modo `"x"` impede só a *aplicação* de sobrescrever. Quem tem acesso ao disco apaga o arquivo. A assinatura detecta alteração, mas **não detecta remoção**.
- **Ação (CP3):** criar uma tabela `declaracoes` no Supabase sem `UPDATE`/`DELETE` para o papel da aplicação (`REVOKE` + RLS + trigger que rejeita), guardando o hash da versão anterior. Para detectar remoção, ancorar o último hash no registro auditável, que já tem cadeia HMAC.

---

## Monitoramento e IA

### 11. Logs completos ✅
- **Evidência:** `RegistroAuditavel` tem duas trilhas (operacional com 90 dias, auditoria com 5 anos), cadeia HMAC com âncora selada, `verificar_cadeia` e minimização automática. A correlação por requisição é feita com `ContextVar`.
- **Ressalva:** "todas as ações críticas" só está provado para o que existe (IA, interruptores, feedback, declaração). Login, aprovação de ONG pelo admin, aprovação do caixa e aceite/recusa de oferta só vão ter log quando a API existir.
- **Argumento a favor de vocês:** o slide da Aula 6 trata "logs completos" como **risco** (vazamento). A formulação "completo em cobertura, mínimo em conteúdo" responde ao checklist e ao slide ao mesmo tempo. Usem isso na apresentação.

### 12. Observabilidade proativa ✅
- **Evidência:** linha de base mediana/MAD por (sinal, chave, hora×dia), z robusto com níveis atenção (3,5), alerta (7) e crítico, freio automático reversível (120 → 10 req/min por 15 min) e drift por PSI. A demo detectou 4/5 anomalias.
- **Ressalva:** o freio continua tendo um **teto estático** (120/min). Isso é aceitável como último recurso, mas expliquem que é a linha de base que o aciona, não o teto. Outro ponto: o estado da linha de base fica **em memória**, então some ao reiniciar e não é compartilhado entre réplicas. No deploy, isso precisa de persistência ou do aviso "aquecimento de N dias".

### 13. RLHF em 4 passos ✅
- **Evidência:** regra 10.4 + SDD 4.3. Os 4 passos são sugerir → corrigir → validar → retreinar com portão. Há código (`feedback.py`), testes e uma demo com atacante (o envenenamento foi barrado na validação e o retreino ingênuo foi barrado no portão).
- **Risco de interpretação:** se o professor espera os 4 passos **clássicos** (pré-treino → coleta de preferências → modelo de recompensa → otimização por PPO), os 4 passos de vocês não coincidem com eles. O documento cita os clássicos, mas não mapeia um no outro.
- **Ação:** uma tabela de 4 linhas, "passo clássico → equivalente aqui → por que adaptado" (por exemplo, "modelo de recompensa → portão de promoção com teste fixo"). Isso deixa claro que a adaptação é consciente, não um mal-entendido.

---

## Documentação

### 14. SDD, PRD e `NUMERIC` ❌
- **SDD/PRD:** existem, com rastreabilidade requisito → código → teste (SDD §9) e decisões D1–D8. Faltam: a decisão do item 5 **contra** o checklist (registrar como D9, com a justificativa), GRC (item 9), o fluxo do pedido (item 2) e o fluxo da declaração no banco (item 10).
- **`NUMERIC` em vez de `INTEGER`:** **não existe nenhum esquema relacional** no repositório (nenhum `CREATE TABLE`, nenhuma migração). O `dicionario-de-dados.md` ainda descreve colunas como `int`. A restrição não foi cumprida, nem dá para verificar.
- **Achado relacionado:** o caixa solidário usa `float` em Python (`TETO_POR_ENTREGA = 40.0`). Dinheiro em ponto flutuante é um erro clássico (0,1 + 0,2 ≠ 0,3). Quando o esquema for criado, use `NUMERIC(10,2)` no banco e `Decimal` no código. Esse é provavelmente o motivo da regra do professor.
- **Pergunta para levar ao professor:** a regra vale também para chaves primárias e contadores (`n_ofertas_ong`, `hora`)? Para IDs, `UUID`/`TEXT` faz mais sentido que `NUMERIC`. Sem resposta, a opção segura é `NUMERIC` para toda quantidade, contagem e valor, e `UUID` para chaves.
- **Ação:** `db/schema.sql` (ou uma migração do Supabase) com todas as tabelas do SDD §5, `NUMERIC` em todo campo numérico, RLS e a tabela de declarações só de inclusão. Atualizar o dicionário de dados de `int` para `NUMERIC`. Um teste simples (`grep -i "integer\|\bint\b" db/*.sql` falha o pipeline) fecha o item com evidência.

---

## Prioridade sugerida até 15/10

| Ordem | Ação | Itens | Esforço |
|:-:|---|---|---|
| 1 | Decidir a leitura do item 5 e implementar o filtro de impasse (com exceção via hub) | 5, 14 | Médio |
| 2 | `db/schema.sql` com `NUMERIC`, RLS e tabela de declarações só de inclusão; dicionário atualizado; `Decimal` no caixa | 10, 14 | Médio |
| 3 | Seção GRC no SDD + RNF de conformidade no PRD | 9 | Baixo |
| 4 | SDD: fluxo do pedido, mapeamento do RLHF clássico, D9 | 2, 13, 14 | Baixo |
| 5 | Disponibilidade do doador ("disponível até") como restrição dura | 4 | Médio (afeta a simulação e o retreino) |
| 6 | CP3: teste que garante esquema em toda rota; guardrail nos campos de texto livre restantes | 7 | Baixo, depois da API |
| 7 | CP2: container de inferência isolado | 8 | Médio |
