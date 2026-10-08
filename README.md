# Rede Alimenta IA

Plataforma com **IA e DevSecOps** que conecta, em tempo real, doadores de alimentos a ONGs na Grande São Paulo. Ela prioriza lotes, prevê descarte e aproveita **frete de retorno** para reduzir o desperdício e combater a fome.

> Projeto Integrador FIAP · Tecnólogo em Inteligência Artificial · Prof. M.Sc. Oerton Fernandes · 2026

---

## O problema

A comida sobra onde há comércio e a fome está na periferia. No recorte do projeto, **85% dos doadores comerciais** ficam em setores de vulnerabilidade baixíssima ou muito baixa, e **77% das ONGs** em setores de vulnerabilidade alta ou muito alta (IPVS 2022, SEADE). Além da distância, a comida pronta fora da geladeira dura só **3 horas**.

## Como a plataforma resolve

1. **Cadastro seguro:** o doador descreve o lote em texto livre. Um modelo de embeddings (Hugging Face) sugere categoria e armazenamento, o doador confirma e o **sistema calcula a validade**, sem confiar no valor digitado. **Tudo que entra é validado** (esquema estrito, dígito verificador de CPF/CNPJ, guardrail, regra).
2. **Questionário + Declaração de Doação:** as respostas viram um documento **assinado (RSA-PSS) e imutável**, que registra o que foi doado, por quem e em que condições (Lei 14.016/2020). Alimento exposto em buffet ou com embalagem violada é bloqueado.
3. **Modelo 1: prioridade** (CRÍTICA, ALTA, MÉDIA, BAIXA), com **piso de segurança**: o modelo nunca rebaixa um caso crítico.
4. **Matching** com filtros obrigatórios (o que a ONG aceita, cozinha, refrigeração, freezer, janela de recebimento) e score por **tempo até a ONG poder receber**, capacidade, **vulnerabilidade do setor** (30% do peso), complementaridade busca × entrega e **pedidos abertos das ONGs**.
5. **Transporte em cascata:** ONG ou voluntário, doador, motorista de retorno, transportadora com rota A→B vazia e, só em último caso, entregador de app pago por um **caixa solidário** (sem lucro, com tetos e aprovação externa).
6. **Modelo 2: risco de descarte**, que decide quando vale gastar o caixa para não perder a comida.
7. **Segurança e governança:** log completo em cobertura e mínimo em conteúdo (cadeia HMAC), **observabilidade** que avisa quando algo sai do normal, IA desligável, ciclo de feedback humano protegido contra envenenamento, catálogo de dados verificado por teste.

**Diferenciais** em relação a plataformas existentes (ex.: Comida Invisível): IA de prioridade e descarte, frete de retorno, ranking por vulnerabilidade social e validade calculada pelo sistema.

## Resultados (ano simulado, regras v2.0)

| Indicador | Valor |
|---|---|
| Lotes simulados | 25.045 (set/2025–ago/2026), 6,8% bloqueados (validade ou questionário) |
| Refeições geradas | ~921 mil (345 t salvas) |
| Taxa de descarte | 15,2% (v1.1: 11,4%: os filtros novos recusam o que a ONG não comporta) |
| Tempo mediano de match | 27,8 min |
| Matches complementares (busca × entrega) | 56% (redundantes: 10%) |
| Modelo 1 (teste) | acurácia 92,8% · recall CRÍTICA 95,2% |
| Modelo 2 (teste) | ROC-AUC 0,84 · PR-AUC 0,55 (heurística: 0,27) · recall 83,4% (meta 85%) |
| NLP de texto livre (teste) | 75,3% de acurácia em 4,4 ms/texto (baseline zero-shot NLI: 50% em 3,8 s) |
| Observabilidade | 4 de 5 anomalias injetadas detectadas (o lote 10× o normal fica dentro da variação natural); alarmes falsos < 0,5% em dados normais |
| Ciclo de feedback (RLHF adaptado) | NLP de 75,3% → 85,3% com rótulos humanos validados; atacante em quarentena (0 rótulos aceitos) |
| Qualidade de dados | 15/15 checagens OK |
| Matriz STRIDE | 34 ameaças · residual sem riscos altos ou críticos |
| Testes automatizados | 181 |

---

## Estrutura

```
src/
├── regras/           regras de negócio puras (validade, prioridade, matching, questionário, caixa, refeições)
├── validacao/        esquemas de entrada estritos, dígito verificador CPF/CNPJ, verificação na Receita
├── seguranca/        guardrail, minimização/pseudônimo, segredos, Declaração assinada + PDF, Matriz STRIDE
├── observabilidade/  registro auditável (cadeia HMAC), anomalias por linha de base, freio, drift (PSI)
├── models/           features, treino, NLP, artefatos com hash, controle da IA, feedback humano (RLHF adaptado)
├── governanca/       catálogo de dados (classe, base legal, retenção, dono) e qualidade de dados
└── data/             curadoria IPVS, premissas (parametros.py), entidades, simulação, gerador
data/
├── reference/     setores censitários reais + índice de vulnerabilidade por região
└── processed/     dataset simulado (lotes, eventos, doadores, ONGs, hubs, transportadores)
docs/              regras de negócio, PRD, SDD, dicionário de dados, STRIDE, governança (GRC/LGPD)
notebooks/         análise exploratória e resultados (narrativa visual)
reports/           métricas dos modelos, avaliação do NLP e do guardrail
tests/             regras, questionário, validação, declaração, logs, observabilidade, IA, feedback, governança
```

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt --extra-index-url https://download.pytorch.org/whl/cpu

python -m src.data.curadoria_ipvs      # baixa o IPVS 2022 (83 MB) e valida o SHA-256
python -m src.data.gerar_dataset       # gera o dataset (semente 42, ~3 min)
python -m src.models.treinar           # treina e avalia os Modelos 1 e 2
python -m src.models.avaliar_nlp       # baixa o modelo HF (~490 MB) e avalia NLP + guardrail
python -m src.seguranca.stride         # gera a Matriz STRIDE (xlsx + tabela)
python -m src.governanca.qualidade     # 15 checagens de qualidade de dados (sai com erro se falhar)
python -m src.observabilidade.demo     # observabilidade no ano simulado (alarmes falsos e anomalias injetadas)
python -m src.seguranca.exemplo_declaracao  # declaração assinada de exemplo + PDF em docs/exemplos/
python -m src.models.demo_feedback     # ciclo de feedback humano com envenenamento simulado
pytest                                 # 181 testes
```

## Documentação

- [Regras de negócio v2.0](docs/regras-de-negocio.md): fonte de verdade de todo o sistema
- [PRD](docs/prd.md) (requisitos de produto) · [SDD](docs/sdd.md) (arquitetura)
- Governança: [política de IA e dados](docs/governanca/politica-governanca-ia.md) · [análise de agência da IA](docs/governanca/analise-agencia-ia.md) · [matriz de controles](docs/governanca/matriz-controles.md) · [inventário de dados (LGPD)](docs/governanca/inventario-de-dados.md) · [RIPD](docs/governanca/ripd.md)
- [Exemplo de Declaração de Doação (PDF)](docs/exemplos/declaracao-exemplo.pdf)
- [Dicionário de dados](docs/dicionario-de-dados.md)
- [Matriz STRIDE](docs/stride/matriz-stride.md) · [planilha](docs/stride/matriz-stride.xlsx)
- [Notebook de análise e resultados](notebooks/01_eda_e_resultados.ipynb)

## Fontes de dados

| Fonte | Uso |
|---|---|
| IPVS 2022, Fundação SEADE | Vulnerabilidade por setor censitário, posição das entidades |
| TACO 4ª ed., NEPA/UNICAMP | kcal por categoria (conversão kg → refeições) |
| PAT, Portaria Interministerial nº 66/2006 | 700 kcal por refeição principal |
| WRAP / FareShare | 420 g por refeição (preparados) |
| Lei 14.016/2020 | Base legal da doação de excedentes |

## Roadmap

- [x] **CP1: MVP de IA** · dataset estruturado · modelos locais · Matriz STRIDE
- [ ] **CP2: DevSecOps** · Dockerfile + Compose · GitHub Actions · Bandit + Trivy
- [ ] **CP3: Deploy e impacto** · API FastAPI + Streamlit · Supabase · URL pública · LGPD · pitch
