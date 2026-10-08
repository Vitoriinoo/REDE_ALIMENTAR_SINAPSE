# PRD: Rede Alimenta IA

> **Documento de Requisitos de Produto** · v2.0 · 2026-10-05
> O **o quê** e o **porquê**. O **como** está no [SDD](sdd.md), e as regras detalhadas em [regras-de-negocio.md](regras-de-negocio.md).

---

## 1. Problema

Na Grande São Paulo, a comida sobra onde há comércio e a fome está na periferia. No recorte do projeto, **85% dos doadores comerciais** ficam em setores de vulnerabilidade baixíssima ou muito baixa (IPVS 2022), e **77% das ONGs** em setores de vulnerabilidade alta ou muito alta. Além da distância, o tempo pesa: comida pronta fora da geladeira dura **3 horas**.

Hoje a doação depende de contato informal (WhatsApp, telefone). Isso gera quatro problemas:
- **Perda:** o lote vence enquanto alguém procura uma ONG e um transporte.
- **Desigualdade:** a doação vai para quem está perto, e não para quem mais precisa.
- **Insegurança sanitária:** ninguém registra em que condição o alimento saiu.
- **Desconfiança:** não há rastro de quem doou o quê, quem recebeu e quem pagou o frete.

## 2. Visão

> Conectar, em minutos, o excedente de alimentos a quem mais precisa, com a decisão crítica sempre na mão de uma pessoa e cada passo registrado de forma auditável.

## 3. Personas

| Persona | Quem é | Dor principal | O que o produto entrega |
|---|---|---|---|
| **Doador PJ** | Restaurante, mercado, padaria, indústria | "Sobrou e não sei para quem doar a tempo" | Cadastro em texto livre, destino em minutos, declaração que o protege (Lei 14.016) |
| **Doador PF** | Pessoa com alimento lacrado em casa | "Quero doar, mas não sei onde" | Doação de não perecível lacrado, entrega num hub |
| **ONG (cozinha comunitária)** | Serve refeições no local | "Recebo o que não consigo preparar ou guardar" | Filtro pelo que a estrutura comporta (cozinha, refrigeração, freezer), janela de recebimento |
| **ONG (distribui cestas)** | Entrega alimento às famílias | "Falta justamente o que eu preciso" | **Pedidos** de alimento, mural para doadores |
| **Transportador** | Voluntário, motorista de retorno, transportadora | "Volto vazio" | Coleta no caminho de volta, endereço só após o aceite |
| **Gestor do caixa** | Externo às ONGs | "Preciso de controle sobre cada real" | Aprovação acima do teto, livro-caixa transparente |
| **Admin** | Equipe da plataforma | "Preciso confiar em quem entra" | Verificação de CNPJ, revisão humana, painel de alertas |

## 4. Objetivos e métricas de sucesso

| Objetivo | Métrica | Meta | Simulado v2.0 |
|---|---|---|---|
| Salvar comida | Taxa de descarte dos lotes aceitos | < 20% | **15,2%** |
| Impacto social | Refeições geradas por ano | Mostrar por região | **~921 mil** (345 t) |
| Rapidez | Tempo mediano até o aceite da ONG | ≤ 30 min (benchmark de mercado: ~8 min) | **27,8 min** |
| IA útil: prioridade | Recall da classe CRÍTICA (M1) | ≥ 90% | **95,2%** |
| IA útil: descarte | Recall de descarte (M2) / PR-AUC vs. heurística | ≥ 85% / acima da heurística | **83,4%** / 0,55 vs. 0,27 |
| Uso eficiente da logística | Matches complementares (busca × entrega) | Maioria | **56%** (redundantes: 10%) |
| Segurança | Achados ALTO/CRÍTICO de SAST e dependências | 0 em produção | CP2 |
| Rastreabilidade | Decisões com registro auditável íntegro | 100% | Cadeia HMAC verificada em teste |

> **Recall do M2 no teste (83,4%) ficou abaixo da meta de 85%.** O limiar foi escolhido na validação, que é o certo metodologicamente, e o teste mostra a queda na troca de período. Fica registrado como risco e como gatilho de revisão no ciclo de feedback (regras 10.4).

## 5. Requisitos funcionais

| ID | Requisito | Regra | Status |
|---|---|---|---|
| RF-01 | Doador cadastra lote em texto livre; a IA sugere categoria e armazenamento; o doador confirma | 4.4 | Regra + modelo prontos; API no CP3 |
| RF-02 | Sistema **calcula** a validade efetiva (não confia no valor digitado) e bloqueia abaixo do mínimo | 4.2, 4.3 | Pronto |
| RF-03 | CPF só doa não perecível lacrado | 4.1 | Pronto |
| RF-04 | Questionário obrigatório gera **Declaração de Doação** assinada, imutável e com PDF | 4.5 | Pronto |
| RF-05 | Toda entrada é validada (esquema estrito, dígito verificador, guardrail, regra) | 4.6 | Pronto |
| RF-06 | CNPJ verificado: dígito verificador (inclusive alfanumérico) + Receita (BrasilAPI) + admin | 6.3 | Pronto |
| RF-07 | Modelo 1 classifica prioridade, com piso de segurança | 5, 10.3 | Pronto |
| RF-08 | Ranking de ONGs com filtros obrigatórios e score auditável | 6.1 | Pronto |
| RF-09 | ONG declara capacidades, janela de recebimento e categorias aceitas | 6.4 | Pronto |
| RF-10 | ONG **pede** alimentos (mural + bônus no ranking) | 6.5 | Pronto (simulação); API no CP3 |
| RF-11 | Complementaridade busca × entrega como preferência | 6.6 | Pronto |
| RF-12 | Transporte em cascata (gratuito antes do pago), cadeia fria e rota expressa | 7 | Pronto |
| RF-13 | Modelo 2 decide quando vale acionar o entregador pago | 8 | Pronto |
| RF-14 | Caixa solidário com tetos e aprovação externa | 9 | Pronto |
| RF-15 | Dashboard com impacto, IA e segurança | 12 | CP3 |

## 6. Requisitos não funcionais

| ID | Requisito | Como é atendido |
|---|---|---|
| RNF-01 **Segurança** | Autorização fora do modelo; menor privilégio; segregação de funções | Regras no código; perfis únicos; quem pede não aprova |
| RNF-02 **Privacidade (LGPD)** | Minimização, pseudonimização, retenção definida | HMAC de documentos e atores; catálogo de dados verificado por teste; RIPD |
| RNF-03 **Rastreabilidade** | Log completo em cobertura, mínimo em conteúdo, à prova de adulteração | Duas trilhas, cadeia HMAC, 90 dias / 5 anos |
| RNF-04 **Observabilidade** | Avisar no desvio, não só no teto | Linha de base robusta, 3 níveis, freio automático, PSI |
| RNF-05 **Controle da IA** | IA desligável, saída validada, toda chamada registrada | Camada de controle única (`src/models/controle.py`) |
| RNF-06 **Integridade da IA** | Artefato verificado; feedback não envenena o modelo | SHA-256 antes do load; validação de feedback + portão de promoção |
| RNF-07 **Desempenho** | Sugestão do NLP < 50 ms; ranking < 200 ms | NLP por embeddings: 4,4 ms/texto (75,3% de acurácia) |
| RNF-08 **Custo** | Stack gratuita | Python, FastAPI, Streamlit, Supabase, Render/HF, GitHub Actions |
| RNF-09 **Qualidade** | Testes automatizados e qualidade de dados no pipeline | 181 testes; 15 checagens de qualidade de dados |

## 7. Fora de escopo

- Processar pagamento (a plataforma só mantém o livro-caixa; o pagamento acontece fora).
- Roteirização multi-parada de frota (o projeto faz a escolha de transporte por lote).
- Integração real com apps de entrega (simulada).
- App mobile nativo (a interface é web).

## 8. Premissas e riscos de produto

| Premissa / risco | Mitigação |
|---|---|
| Dados reais não estão disponíveis | Dataset simulado e **calibrado** com fontes públicas (IPVS, TACO, PAT, WRAP), com as premissas documentadas em `src/data/parametros.py` |
| A complementaridade busca × entrega pode custar comida | Calibrada para desempatar entre ONGs acessíveis: custo de ~0,2 p.p. de descarte (regras 6.1) |
| Filtros mais rígidos (v2.0) aumentam "sem ONG elegível" | Esperado e mostrado com transparência: o descarte simulado foi de 11,4% (v1.1) para 15,2% (v2.0), porque o sistema passou a recusar o que a ONG não comporta |
| Doador declara falso no questionário | Inspeção na entrega + declaração assinada (responsabilidade) + alerta de reincidência |
| Ataque ao feedback (envenenamento) | Validação em 4 camadas + portão com teste fixo e aprovação humana |

## 9. Marcos

| Marco | Entregas | Data |
|---|---|---|
| CP1: IA | Dataset, modelos, STRIDE, regras v2.0, governança | ✅ |
| CP2: DevSecOps | Docker + Compose, GitHub Actions, Bandit + Trivy, security gate | Em andamento |
| CP3: Deploy | API FastAPI, dashboard Streamlit, Supabase, URL pública, LGPD | Em andamento |
| **Apresentação** | Pitch + dashboard em sala | **15/10/2026** |
