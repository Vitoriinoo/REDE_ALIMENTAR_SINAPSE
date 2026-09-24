# Rede Alimenta IA

Plataforma com **IA e DevSecOps** que conecta, em tempo real, doadores de alimentos a ONGs na Grande São Paulo. Ela prioriza lotes, prevê descarte e aproveita **frete de retorno** para reduzir o desperdício e combater a fome.

> Projeto Integrador FIAP · Tecnólogo em Inteligência Artificial · Prof. M.Sc. Oerton Fernandes · 2026

---

## O problema

A comida sobra onde há comércio e a fome está na periferia. No recorte do projeto, **85% dos doadores comerciais** ficam em setores de vulnerabilidade baixíssima ou muito baixa, e **77% das ONGs** em setores de vulnerabilidade alta ou muito alta (IPVS 2022, SEADE). Além da distância, a comida pronta fora da geladeira dura só **3 horas**.

## Como a plataforma resolve

1. **Cadastro seguro:** o doador descreve o lote em texto livre. Um modelo de embeddings (Hugging Face) sugere categoria e armazenamento, o doador confirma e o **sistema calcula a validade**, sem confiar no valor digitado.
2. **Modelo 1: prioridade** (CRÍTICA, ALTA, MÉDIA, BAIXA) no momento do cadastro.
3. **Matching** com ranking de ONGs por proximidade, capacidade, compatibilidade e **vulnerabilidade do setor** (30% do peso).
4. **Transporte em cascata:** ONG ou voluntário, doador, motorista de retorno, transportadora com rota A→B vazia e, só em último caso, entregador de app pago por um **caixa solidário** (sem lucro, com tetos e aprovação externa).
5. **Modelo 2: risco de descarte**, que decide quando vale gastar o caixa para não perder a comida.

**Diferenciais** em relação a plataformas existentes (ex.: Comida Invisível): IA de prioridade e descarte, frete de retorno, ranking por vulnerabilidade social e validade calculada pelo sistema.

## Resultados do Checkpoint 1 (ano simulado)

| Indicador | Valor |
|---|---|
| Lotes simulados | 25.939 (set/2025–ago/2026) |
| Refeições geradas | ~1,1 milhão (416 t salvas) |
| Taxa de descarte | 11,4% |
| Modelo 1 (teste) | acurácia 92,3% · recall CRÍTICA 95% |
| Modelo 2 (teste) | ROC-AUC 0,83 · PR-AUC 0,44 (heurística atual: 0,25) · recall 86% |
| NLP de texto livre (teste) | 76% de acurácia em 4,6 ms/texto (baseline zero-shot NLI: 49% em 3,3 s) |
| Matriz STRIDE | 27 ameaças · residual sem riscos altos ou críticos |
| Testes automatizados | 60 |

---

## Estrutura

```
src/
├── regras/        regras de negócio puras (validade, prioridade, matching, caixa, refeições); a API vai reutilizar
├── data/          curadoria IPVS, premissas (parametros.py), entidades, simulação, gerador
├── models/        features (controle de vazamento), treino, NLP (embeddings + exemplos), artefatos com hash
└── seguranca/     guardrail de entrada, Matriz STRIDE (fonte única)
data/
├── reference/     setores censitários reais + índice de vulnerabilidade por região
└── processed/     dataset simulado (lotes, eventos, doadores, ONGs, hubs, transportadores)
docs/              regras de negócio, dicionário de dados, STRIDE
notebooks/         análise exploratória e resultados (narrativa visual)
reports/           métricas dos modelos, avaliação do NLP e do guardrail
tests/             regras, guardrail, integridade de artefatos
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
pytest                                 # 60 testes
```

## Documentação

- [Regras de negócio](docs/regras-de-negocio.md): fonte de verdade de todo o sistema
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
