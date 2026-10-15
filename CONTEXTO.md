# Contexto do projeto: por que a Rede Alimenta IA existe e como ela tira nota máxima

Leia este arquivo antes de mexer no repositório. Ele explica o **porquê** do projeto, o que o professor avalia, como cada entregável vira nota e as regras de trabalho que não podem ser quebradas. O **como** está no [README](README.md), e a fonte de verdade das regras é [docs/regras-de-negocio.md](docs/regras-de-negocio.md).

> Projeto Integrador FIAP · Tecnólogo em Inteligência Artificial, 1º ano · Prof. M.Sc. Oerton Fernandes · 2026
> Entrega e apresentação: **15/10/2026**, em sala, com a plataforma funcionando e o dashboard aberto.

---

## 1. O porquê: o problema social

O Brasil vive um paradoxo: toneladas de comida vão para o lixo enquanto milhões de pessoas passam fome. A sobra existe e a necessidade existe, mas as duas não se encontram a tempo. A missão do enunciado é **usar IA para ligar o excedente dos doadores à necessidade real das ONGs, em tempo real**, com foco em impacto social direto e eficiência logística urbana.

No nosso recorte (Grande São Paulo: 8 macrorregiões da capital + Guarulhos, Osasco, Santo André, São Bernardo, São Caetano, Diadema e Mauá), os dados mostram três obstáculos:

1. **Distância social.** 85% dos doadores comerciais ficam em setores de vulnerabilidade baixíssima ou muito baixa, e 77% das ONGs em setores de vulnerabilidade alta ou muito alta (IPVS 2022, Fundação SEADE). A comida sobra onde há comércio, e a fome está na periferia.
2. **Tempo.** Comida pronta fora da geladeira dura no máximo 3 horas. Uma doação que demora para achar destino vira lixo.
3. **Transporte.** Muita ONG não tem carro e muito doador não pode entregar. Sem resolver o frete, o match não vira refeição.

Por isso a solução não é só um cadastro de doações. Ela **prioriza** o que vai estragar primeiro, **escolhe a ONG** pelo tempo até receber e pela vulnerabilidade da região, **resolve o transporte** em cascata (das opções gratuitas, como o frete de retorno de um motorista que volta vazio, até um entregador pago por um caixa solidário só quando o risco de descarte justifica) e **protege** os dados de quem doa e de quem recebe.

**Diferenciais** frente a plataformas existentes (ex.: Comida Invisível): IA de prioridade e de risco de descarte, frete de retorno, ranking por vulnerabilidade social e validade calculada pelo sistema, sem confiar no valor digitado.

## 2. O que o professor pede

### 2.1 Entregáveis por checkpoint

| Checkpoint | Foco | Entregáveis |
|---|---|---|
| **CP1: MVP de IA** | Validar o núcleo inteligente e modelar os riscos iniciais | Dataset estruturado (público/simulado) · modelo funcional local · Matriz de Ameaças e Riscos (STRIDE) |
| **CP2: DevSecOps** | Engenharia moderna e segurança contínua no ciclo da IA | Dockerfile + Docker Compose · pipeline GitHub Actions · relatórios SAST (Bandit e Trivy) |
| **CP3: Deploy e impacto** | Plataforma pública, impacto social, LGPD e resiliência na nuvem | URL pública (Render ou Hugging Face) · banco em nuvem (Supabase ou MongoDB Atlas) · README completo · pitch final |

Os checkpoints servem para organizar o trabalho; o professor cobra **tudo junto** na entrega final.

### 2.2 Stack exigida (100% gratuita)

Python 3.10+ · Scikit-learn e Pandas · Hugging Face · FastAPI com Swagger · Streamlit ou Gradio · Render ou Hugging Face · Supabase ou MongoDB Atlas · GitHub Actions · Bandit e Trivy · Docker e Docker Compose.

### 2.3 Apresentação final (dashboard)

O grupo apresenta a plataforma funcionando. O dashboard precisa mostrar:

- **Impacto social:** kg de alimentos salvos e refeições geradas por região
- **IA:** acurácia do modelo na predição de descarte e tempo médio de match doador × ONG
- **Segurança:** saúde do pipeline, vulnerabilidades mitigadas (SAST) e status dos security gates

E no formato: **gráficos dinâmicos** ("a pulsação da rede" ao vivo), **mapas de calor** das áreas de maior carência atendida e **alertas visuais** vermelho/amarelo para lotes com validade crítica.

### 2.4 Rubrica

| Eixo | Peso | O que conta |
|---|:-:|---|
| **Impacto Social** | 30% | Relevância para a população, utilidade prática, empatia no design |
| **Qualidade da IA** | 30% | Eficácia técnica do modelo, curadoria de dados abertos, uso correto de bibliotecas gratuitas |
| **DevSecOps** | 20% | Maturidade do CI/CD, segurança estática (SAST), eficiência da containerização |
| **Engenharia & Defesa** | 20% | Qualidade do código, documentação técnica (README), clareza na defesa do pitch |

## 3. A estratégia para a nota máxima

A ideia central: **cada critério da rubrica tem uma evidência que o professor consegue abrir ou ver rodando.** Não basta dizer que é seguro ou que a IA é boa; mostramos o número, o arquivo e o teste.

Três princípios guiam todas as escolhas:

1. **Funcionar de verdade é melhor que prometer.** Uma URL pública que cadastra um lote ao vivo vale mais que um slide. Tudo que está no pitch existe no código.
2. **Ser honesto com os números.** Acurácia de 92% com o motivo explicado (o rótulo tem ruído de triador humano de propósito, para não haver acurácia artificial de 100%) convence mais que 99% sem explicação. Metas não batidas aparecem como risco residual documentado.
3. **A IA recomenda, a regra decide.** Toda decisão crítica tem regra rígida no código, fallback quando o modelo é desligado e log auditável. Isso ganha ponto em Qualidade da IA e em DevSecOps ao mesmo tempo.

### 3.1 Como cada eixo vira nota

| Eixo | O que mostramos | Onde está a evidência |
|---|---|---|
| **Impacto Social (30%)** | 352 t de alimento salvo, ~951 mil refeições, descarte de 17,8% (meta < 20%), mapa de calor por vulnerabilidade, ranking que dá 30% do peso à vulnerabilidade do setor, transporte que não exclui ONG sem carro, telas simples para doador e ONG | Aba *Impacto social* do dashboard · [regras §6 e §7](docs/regras-de-negocio.md) · [PRD](docs/prd.md) |
| **Qualidade da IA (30%)** | Dataset de 24 mil lotes calibrado com fontes abertas (IPVS/SEADE, TACO, PAT, WRAP); split temporal; Modelo 1 (prioridade) com 92,0% de acurácia e 94,3% de recall na classe CRÍTICA; Modelo 2 (descarte) com recall de 87,1% e PR-AUC 0,65 contra 0,28 da heurística; NLP de embeddings do Hugging Face com 80,3% contra 49,7% do zero-shot; piso de segurança; ciclo de feedback com defesa contra envenenamento | Aba *Qualidade da IA* · [reports/metricas_modelos.json](reports/metricas_modelos.json) · [notebook](notebooks/01_eda_e_resultados.ipynb) · [dicionário de dados](docs/dicionario-de-dados.md) |
| **DevSecOps (20%)** | Pipeline testes → Bandit → build + Trivy → security gate → deploy; 22 achados → 0; Docker endurecido (usuário sem privilégio, sem pip na imagem, read-only); inferência em container isolado sem segredo e sem internet; deploy só com o gate aprovado | Aba *Segurança* · [.github/workflows/ci.yml](.github/workflows/ci.yml) · [reports/sast/](reports/sast) (antes e depois) · [Dockerfile](Dockerfile) · [docker-compose.yml](docker-compose.yml) |
| **Engenharia & Defesa (20%)** | Código modular em `src/` com regras compartilhadas entre simulação e API, 230 testes, README completo, PRD, SDD com decisões D1–D13, STRIDE com 34 ameaças, governança (LGPD, RIPD, matriz de controles), pitch com roteiro | [README](README.md) · [SDD](docs/sdd.md) · [STRIDE](docs/stride/matriz-stride.md) · [governança](docs/governanca) |

### 3.2 Entregáveis → arquivo → situação

| Entregável | Onde | Situação |
|---|---|---|
| Dataset estruturado | `data/processed/` (gerado por `python -m src.data.gerar_dataset`, seed 42) + `data/reference/` (IPVS 2022) | Pronto |
| Modelo funcional local | `src/models/` (`python -m src.models.treinar`), métricas em `reports/` | Pronto |
| Matriz de riscos (STRIDE) | `docs/stride/matriz-stride.md` + `.xlsx` (34 ameaças, P×I 1–5, risco inerente e residual) | Pronto |
| Dockerfile + Compose | `Dockerfile` (alvos `api`, `inferencia`, `dashboard`, `render`) e `docker-compose.yml` | Pronto |
| Pipeline CI/CD | `.github/workflows/ci.yml` | Pronto |
| Relatórios SAST (Bandit e Trivy) | `reports/sast/` (arquivos `-antes` e atuais + `resumo.json`) | Pronto: 22 → 0 |
| URL pública | API no **Render** (alvo `render`) e dashboard no **Streamlit Community Cloud** | Código pronto; falta publicar e colocar as URLs reais no README |
| Banco em nuvem | **Supabase** com `db/schema.sql` (NUMERIC, UUID, RLS, papéis de menor privilégio, tabela só de inclusão) | Código pronto; falta carregar no projeto Supabase |
| README completo | `README.md` | Pronto; atualizar URLs e a contagem de testes |
| Pitch final | Deck de 12 slides com notas de fala | Pronto; faltam nomes do grupo na capa e URLs no slide da demo |

### 3.3 KPIs do dashboard → onde aparecem

| KPI exigido | Onde no dashboard |
|---|---|
| Kg salvos e refeições por região | *Painel de impacto* → aba *Impacto social* (barras por região + mapa de calor) |
| Acurácia da IA (predição de descarte) | aba *Qualidade da IA* (acurácia + recall/F1, porque descarte é classe rara e acurácia sozinha engana) |
| Tempo médio de match | aba *Impacto social* (por prioridade: CRÍTICA é ofertada primeiro) |
| Vulnerabilidades mitigadas (SAST) e security gates | aba *Segurança* (antes × depois, status do gate) |
| Gráficos dinâmicos / pulsação da rede | aba *Ao vivo* (lotes cadastrados pela API) |
| Alertas de validade crítica | hoje só na tela *Ofertas da ONG* (🔴 CRÍTICA, 🟠 ALTA, 🟡 MÉDIA). **Lacuna:** a aba *Ao vivo* mostra uma tabela sem destaque (ver §8) |
| Operação real | páginas *Doar alimentos*, *Ofertas da ONG* e *Administração*, liberadas pela chave de acesso de cada papel |

## 4. Decisões que não se reinterpretam

Estas regras foram decididas pelo grupo ou cobradas pelo professor. Não transforme uma proibição em preferência nem mude um limite sem decisão explícita do grupo. Os detalhes estão em [docs/regras-de-negocio.md](docs/regras-de-negocio.md).

- **Dois modelos:** M1 = prioridade (CRÍTICA/ALTA/MÉDIA/BAIXA) no cadastro; M2 = risco de descarte, que decide quando vale gastar o caixa solidário. O modelo **nunca rebaixa** um caso crítico (piso de segurança).
- **Validade é calculada pelo sistema** (preparado em ambiente = preparo + 3 h), nunca aceita do valor digitado. Abaixo da validade mínima da categoria, o cadastro é bloqueado.
- **Pessoa física** só doa não perecível lacrado. O tipo do doador vem da conta autenticada, nunca do corpo da requisição.
- **Match:** o sistema sugere e a ONG aceita, em oferta **sequencial**; após 3 recusas, escala ao admin. A ONG vê o alimento e a logística, nunca quem doou.
- **Impasse "doador só entrega × ONG só busca" é bloqueado**; a única saída é o hub como ponto de encontro, com qualquer transporte da cascata.
- **Transporte em cascata:** gratuitos primeiro; o entregador pago só entra se nenhum gratuito aceitar no prazo **e** o M2 prever alto risco de descarte.
- **Caixa solidário:** a plataforma não guarda dinheiro, só mantém um livro-caixa transparente. Teto automático de R$40 por entrega e R$200 por dia por ONG; acima disso, aprovação de um gestor externo. Dinheiro é `Decimal` no código e `NUMERIC` no banco.
- **Declaração de Doação** (Lei 14.016/2020): documento assinado com RSA-PSS, imutável, numa tabela só de inclusão.
- **Deploy público:** API no Render com M1 e M2 e o NLP desligado (o torch não cabe em 512 MB; sem ele, o doador escolhe a categoria). No Compose local, o NLP roda isolado. Isso é risco residual documentado (SDD, D12).

## 5. Vocabulário que o professor usa (usar nos documentos e no pitch)

- **Risco:** Ativo → Ameaça → Vulnerabilidade → Impacto → Controle → Evidência → Reteste. Risco = Probabilidade × Impacto, escala 1–5 cada; faixas 1–4 Baixo, 5–9 Médio, 10–15 Alto, 16–25 Crítico.
- **Controles:** preventivo, detectivo, corretivo. Menor privilégio, allowlist, validação de saída, minimização de dados (LGPD), logs auditáveis, humano no circuito proporcional ao impacto, rate limit, rollback.
- **Regras de ouro:** a autorização existe fora do modelo; a saída da IA nunca é instrução autorizada; regra de negócio rígida fica no código; leitura antes de escrita, recomendação antes de execução.
- **Frameworks:** OWASP Top 10 for LLM, NIST AI RMF (Governar, Mapear, Medir, Gerenciar), ISO 27001 e 42001, Modelo 5C (Contexto, Credenciais, Capacidades, Controles, Consciência), seis camadas (governança, dados, modelo, aplicação, ferramentas/agentes, infraestrutura).
- STRIDE não aparece nos slides das aulas, mas é entregável: por isso a matriz combina STRIDE com o vocabulário e a pontuação P×I acima.

## 6. Perguntas prováveis na defesa

| Pergunta | Resposta curta |
|---|---|
| Por que dados simulados? | Não existe base pública de doações lote a lote. Simulamos a operação calibrada com fontes abertas (IPVS, TACO, PAT, WRAP), com as fontes documentadas e o gerador reproduzível (seed 42). |
| Por que a acurácia do M1 é 92% e não perto de 100%? | O rótulo inclui ~9% de ruído de "triador humano" e variáveis latentes, de propósito. Sem isso o modelo só copiaria a regra. 92% é praticamente o teto possível. |
| Por que olhar recall e não só acurácia no descarte? | Descarte é classe rara: um modelo que diz "nunca descarta" teria acurácia alta e seria inútil. A meta é recall ≥ 85% (pegar quase toda comida em risco), com o limiar ajustado conscientemente. |
| O que impede a IA de tomar uma decisão errada? | A IA recomenda; a decisão fica na `ControleIA` e nas regras. Há interruptor por modelo, fallback para a regra, piso de segurança e log de toda chamada. |
| Como vocês sabem que está seguro? | Pipeline com Bandit, Trivy e security gate que reprova achado ALTO/CRÍTICO; 22 → 0 com relatórios antes/depois; STRIDE com 34 ameaças e reteste; RLS e papéis de menor privilégio no banco. |
| Por que o tempo de match (26 min) é maior que o benchmark (~8 min)? | O benchmark é de mercado e não filtra cadeia fria, capacidade, disponibilidade nem impasse logístico. Nosso match só conta quando a comida chega a tempo; CRÍTICA é ofertada primeiro. |
| E a LGPD? | Minimização (a ONG não vê o doador), CPF/CNPJ só como HMAC, inventário de dados, RIPD, retenção definida e logs com conteúdo mínimo. |

## 7. Regras de trabalho neste repositório

1. **Português** em código, documentos e mensagens de commit, no padrão `tipo(escopo): descrição` já usado no histórico.
2. **Sem atribuição a ferramentas** nos commits e nos arquivos: o trabalho é do grupo. Nada de trailers `Co-Authored-By` nem menções do tipo "gerado por".
3. **Nunca versionar segredos.** `.env`, `segredos/`, `*.pem`, `*.key` e `var/` ficam fora do Git. Segredos novos saem de `deploy/gerar_segredos.py` e `deploy/preparar_publicacao.py`, que gravam em arquivo e nunca imprimem na tela.
4. **Não alterar os bytes de `data/`, `models/` e `reports/*.csv`** por fim de linha: o `.gitattributes` preserva esses arquivos porque o SHA-256 deles é conferido antes de carregar os modelos.
5. **Testes antes de subir:** `.venv\Scripts\python -m pytest -q` precisa passar. Os 5 testes pulados localmente rodam contra PostgreSQL real no CI.
6. **Números mudam junto com o código.** Se mudar uma regra que afeta a simulação, regenere o dataset, retreine e atualize README, dashboard e pitch com os novos valores. Não edite número à mão.
7. **Regra de negócio é decisão do grupo.** Antes de mudar um limite, uma proibição ou um peso do ranking, pergunte e registre a decisão em `docs/regras-de-negocio.md` e, se for de arquitetura, no SDD (tabela de decisões).
8. **Toda afirmação do pitch precisa de evidência** no repositório (arquivo, teste ou tela). Se não existe, não entra no pitch.

## 8. O que falta para a apresentação

- [ ] Criar o projeto no Supabase e carregar o banco (`python -m src.db.carregar` e `python deploy/configurar_banco.py`)
- [ ] Publicar a API no Render e o dashboard no Streamlit Cloud (passo a passo no README, seção *Deploy*); secret `RENDER_DEPLOY_HOOK` no GitHub
- [ ] **Alertas visuais na aba *Ao vivo*** (o enunciado pede vermelho/amarelo para validade crítica): destacar CRÍTICA/ALTA e as horas restantes de validade em `src/dashboard/paginas/painel.py`
- [ ] Trocar as URLs provisórias do README e do slide da demo pelas reais
- [x] Atualizar a contagem de testes no README (230 = 224 locais + 6 no CI)
- [ ] Nomes do grupo na capa do pitch
- [ ] No dia: abrir a API 1–2 min antes (o Render grátis "dorme" após 15 min sem acesso) e ter um lote de exemplo pronto para cadastrar ao vivo
