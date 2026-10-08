# Política de governança de IA e de dados

> **GRC** (Governança, Riscos e Conformidade) da Rede Alimenta IA, organizado pelas 4 funções do **NIST AI RMF** (Governar, Mapear, Medir, Gerenciar) e alinhado à **ISO/IEC 42001** (sistema de gestão de IA), à **ISO/IEC 27001:2022** e à **LGPD**.

---

## 1. Papéis e responsabilidades (RACI)

Os papéis são genéricos. Cada membro do grupo assume um ou mais, e **quem treina um modelo nunca aprova a promoção dele** (segregação de funções).

| Atividade | Responsável por dados | Responsável pelos modelos de IA | Responsável por segurança | Responsável por produto | Encarregado (DPO) |
|---|:-:|:-:|:-:|:-:|:-:|
| Classificar um dado novo no catálogo | **R** | C | C | I | **A** |
| Treinar / retreinar modelo | C | **R** | I | I | I |
| Aprovar promoção de modelo | I | — (vetado) | **A** | **R** | I |
| Desligar modelo em incidente | I | C | **R/A** | I | I |
| Revisar alertas e freios | I | C | **R/A** | C | I |
| Aprovar ONG | I | I | C | **R/A** | I |
| Responder a titular (LGPD) | C | I | C | I | **R/A** |
| Revisar a Matriz STRIDE | C | C | **R/A** | C | C |

R = executa · A = responde · C = consultado · I = informado

## 2. NIST AI RMF aplicado

| Função | O que fazemos | Artefato |
|---|---|---|
| **Governar** | Regras de negócio versionadas como fonte de verdade; papéis acima; portão de promoção com segregação; política de logs e retenção | `regras-de-negocio.md`, este documento, `feedback.py` |
| **Mapear** | Contexto de uso, personas e impactos (PRD); ameaças por componente (STRIDE); inventário de dados e agência da IA | `prd.md`, `stride/`, `inventario-de-dados.md`, `analise-agencia-ia.md` |
| **Medir** | Métricas dos modelos contra baselines (regra, heurística, ingênuo) num teste temporal fixo; reteste do guardrail; qualidade de dados; drift (PSI); taxa de fallback | `reports/*.json`, `qualidade.py`, `drift.py` |
| **Gerenciar** | Controles preventivos/detectivos/corretivos; desligamento por modelo; rollback; freio automático; resposta a incidente | `controle.py`, `freio.py`, `RegistroDeVersoes` |

## 3. Ciclo de vida do modelo

| Etapa | Regra | Controle |
|---|---|---|
| Dados | Só dado catalogado e aprovado nas checagens de qualidade | `test_governanca.py` falha com coluna não classificada; `qualidade.py` falha com violação |
| Treino | Split temporal; features declaradas; lista de colunas proibidas (vazamento) | `features.py::checar_vazamento` |
| Avaliação | Contra baselines, no conjunto de teste usado uma única vez | `treinar.py` |
| Artefato | SHA-256 nos metadados; carregamento só se bater | `artefatos.py` |
| Promoção | Não piorar no teste fixo, metas mínimas, aprovador ≠ treinador | `portao_de_promocao` |
| Operação | Toda chamada registrada; drift monitorado; desligável | `controle.py`, `drift.py` |
| Aposentadoria | Versão anterior mantida para rollback | `RegistroDeVersoes.rollback` |

## 4. Governança de dados

| Princípio | Regra |
|---|---|
| Inventário | Toda coluna tem classe, base legal, retenção e dono (`src/governanca/catalogo.py`) |
| Minimização | Modelos nunca recebem nome, documento, endereço exato ou texto livre (só o NLP recebe o texto, depois do guardrail) |
| Pseudonimização | Documentos e atores como HMAC com chave fora do código |
| Qualidade | 15 checagens automáticas (unicidade, integridade referencial, domínio, faixas, invariantes de negócio, ausência de dado pessoal em texto) |
| Linhagem | Dataset com SHA-256 nos metadados do modelo → artefato com SHA-256 → versão no registro de versões |
| Retenção | Texto livre e log operacional: 90 dias · contato: 12 meses após a última atividade · auditoria e declarações: 5 anos |
| Direitos do titular | Acesso, correção e eliminação pelo Encarregado. A eliminação **pseudonimiza** os registros de auditoria (o HMAC fica e o vínculo com a pessoa some) para não quebrar a cadeia |

## 5. Gestão de riscos

- **Registro de riscos:** [Matriz STRIDE](../stride/matriz-stride.md), com P × I de 1 a 5, risco inerente e residual, controles preventivo/detectivo/corretivo, evidência e reteste.
- **Revisão:** a cada mudança de regra de negócio (nova versão do documento de regras) ou incidente.
- **Apetite:** nenhum risco residual **Alto** ou **Crítico** em produção. Risco **Médio** exige dono e prazo.

## 6. Conformidade

| Norma / lei | Onde está o mapeamento |
|---|---|
| LGPD | [inventario-de-dados.md](inventario-de-dados.md), [ripd.md](ripd.md) |
| Lei 14.016/2020 (doação de alimentos) | Questionário + Declaração (regras 4.5) |
| ISO/IEC 27001:2022, ISO/IEC 42001, NIST CSF 2.0, OWASP LLM 2025 | [matriz-controles.md](matriz-controles.md) |
