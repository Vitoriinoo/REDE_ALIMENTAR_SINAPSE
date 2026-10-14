# Dicionário de Dados: Rede Alimenta IA

> Dataset **simulado e calibrado com fontes públicas** (IPVS 2022/SEADE, TACO/UNICAMP, PAT, WRAP), 12 meses (set/2025–ago/2026).
> Reprodutível: `python -m src.data.curadoria_ipvs` e depois `python -m src.data.gerar_dataset` (semente 42).
> Premissas da simulação: `src/data/parametros.py` e regras, seção 8.1. **Versão das regras: 2.1** (2026-10-14).
> Classificação, base legal, retenção e dono de cada coluna: `src/governanca/catalogo.py` (verificado por teste).
> **Tipos no banco (v2.1):** a coluna "Tipo" abaixo usa o tipo do **banco** (`db/schema.sql`). Toda quantidade, contagem, medida e valor é `NUMERIC(p,s)`, **nunca** `INTEGER` nem ponto flutuante (checklist do professor, item 14). Dinheiro é `NUMERIC(10,2)`, e as chaves são `UUID` + código legível (`L-000001`) em `TEXT`. Nos CSVs, os mesmos campos aparecem como texto/número do pandas.

**Legenda da coluna "Uso":**
- **M1** = feature do Modelo 1 (prioridade)
- **M2** = feature do Modelo 2 (descarte)
- **alvo** = variável a prever
- **desfecho** = só existe depois da decisão, **proibida como feature** (vazamento de dados)
- **latente** = fator real que o modelo não vê
- **—** = identificação ou apoio

## Visão geral

| Arquivo | Linhas | Grão |
|---|---|---|
| `data/processed/lotes.csv` | 24.135 | 1 doação cadastrada |
| `data/processed/eventos.csv.gz` | ~235 mil | 1 evento da trilha de auditoria |
| `data/processed/pedidos.csv` | 1.414 | 1 pedido de alimento aberto por uma ONG (regras 6.5) |
| `data/processed/doadores.csv` | 300 | 1 doador (210 PJ, 90 PF) |
| `data/processed/ongs.csv` | 60 | 1 ONG (55 aprovadas, 3 pendentes, 2 reprovadas) |
| `data/processed/hubs.csv` | 40 | 1 ponto de encontro validado |
| `data/processed/transportadores.csv` | 160 | 1 transportador (70 voluntários, 65 motoristas de retorno, 25 transportadoras) |
| `data/processed/contexto_diario.csv` | 365 | 1 dia |
| `data/reference/setores_rmsp.csv` | 36.847 | 1 setor censitário real (IPVS 2022) |
| `data/reference/regioes.csv` | 15 | 1 região (8 macrorregiões de SP + 7 municípios) |

**Privacidade (LGPD):** não há nome, CPF, CNPJ, telefone ou endereço em nenhum arquivo. Documentos existem só como `documento_hash` (HMAC-SHA256 com chave secreta). Doadores PF ficam no **centroide do setor censitário**, nunca no endereço.

---

## `lotes.csv`

### Identificação e doador
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `lote_id` | texto | Identificador `L-000001` | — |
| `doador_id` | texto | FK para `doadores.csv` | — |
| `tipo_doador` | `PJ`/`PF` | Tipo de doador | M1, M2 |
| `segmento` | texto | restaurante, mercado, padaria, hortifruti, industria, pf | M2 |
| `regiao` | texto | Região do doador (15 regiões) | M2 |
| `doador_tem_refrigeracao` | bool | Doador possui geladeira/câmara fria | M2 |
| `doador_pode_entregar` | bool | Doador declarou que pode entregar (capacidade, regras 6.6) | M2 |
| `doador_aceita_coleta` | bool | v2.1: falso = doador "só entrega" (restrição, 6.6) | M2 |

### Cadastro (informado pelo doador ou calculado pelo sistema)
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `ts_cadastro` | TIMESTAMPTZ | Momento do cadastro (horário de Brasília) | — (usada no split temporal) |
| `categoria` | texto | preparado, refrigerado, congelado, hortifruti, padaria, nao_perecivel | M1, M2 |
| `armazenamento` | texto | refrigerado, congelado, ambiente | M1, M2 |
| `peso_kg` | NUMERIC | Peso do lote | M1, M2 |
| `descricao_texto` | texto | Descrição livre (entrada do NLP; **pessoal potencial**: retenção de 90 dias) | NLP |
| `texto_adversarial` | bool | Descrição é um payload de ataque (~1,5%) | avaliação do guardrail |
| `tipo_adversarial` | texto | prompt_injection, entrada_gigante, html_script, sql_injection | avaliação do guardrail |
| `ts_preparo` | TIMESTAMPTZ | Hora do preparo (só Preparado) | — |
| `validade_rotulo` | TIMESTAMPTZ | Validade do rótulo (Refrigerado/Congelado) | — |
| `ts_saida_refrigeracao` | TIMESTAMPTZ | Desde quando está fora da refrigeração | — |
| `validade_informada` | TIMESTAMPTZ | Validade informada (Hortifruti, Padaria, Não perecível) | — |
| `validade_efetiva` | TIMESTAMPTZ | **Calculada pelo sistema** (regras 4.2) | — |
| `horas_restantes` | NUMERIC | `validade_efetiva − ts_cadastro`, em horas | M1, M2 |
| `rota_expressa` | bool | Cadeia fria fora da refrigeração (regras 7.5) | M1, M2 |
| `requer_preparo` | bool | Precisa ser cozido antes de consumir (questionário Q4) | M2; filtro de ONG |
| `alergenicos` | texto | Alergênicos declarados (Q3), separados por `\|`; `nenhum` se não há | — (segue para a ONG) |
| `bloqueio_questionario` | texto | Motivos de bloqueio do questionário (4.5), vazio se aceito | — |

### Triagem
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `prioridade` | texto | CRITICA, ALTA, MEDIA, BAIXA: **rótulo do triador humano** (regra + ~9% de discordância) | **alvo M1**; M2 (no teste, usa a predição do M1) |
| `prioridade_regra` | texto | Prioridade pela regra determinística (5.1), sem ruído | baseline, **proibida como feature** |
| `prioridade_operacional` | texto | Nova prioridade após o doador refrigerar (7.5) | desfecho |

### Contexto no momento da decisão
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `hora`, `dia_semana` | NUMERIC | Hora (0–23) e dia (0 = segunda) do cadastro | M2 |
| `mes` | NUMERIC | Mês do cadastro | — (fora do M2: split temporal) |
| `fim_de_semana`, `feriado` | bool | Calendário | M2 |
| `n_ongs_compativeis_10km` | NUMERIC | ONGs elegíveis (aprovadas, com capacidade e compatíveis) num raio de 10 km | M2 |
| `dist_ong_top_km` | NUMERIC | Distância viária até a ONG mais bem ranqueada (vazio se nenhuma) | M2 |
| `min_ate_receber_top` | NUMERIC | Minutos até a ONG do topo poder receber: antecedência + trajeto ou espera da janela (6.1) | M2 |
| `n_transportadores_ativos_raio` | NUMERIC | Transportadores ativos no dia num raio de 12 km | M2 |
| `n_ongs_impasse` | NUMERIC | v2.1: ONGs barradas pelo impasse "só entrega × só busca" (6.6) | M2 |
| `refrigerado_disponivel` | bool | Há veículo refrigerado ativo no raio | M2 |

### Desfecho (proibido como feature)
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `status_final` | texto | ENTREGUE, DESCARTADO, BLOQUEADO (validade abaixo do mínimo ou questionário) | desfecho |
| `descartado` | bool | Lote perdido (vazio para BLOQUEADO) | **alvo M2** |
| `motivo_descarte` | texto | SEM_ONG_ELEGIVEL, NENHUMA_ONG_ACEITOU, SEM_TRANSPORTE, QUEBRA_CADEIA_FRIA, VENCEU_ANTES_DA_ENTREGA, VENCEU_AGUARDANDO_ONG, RECUSADO_NA_INSPECAO, REFRIGERADO_FORA_DA_JANELA, VALIDADE_ABAIXO_DO_MINIMO, QUESTIONARIO | desfecho |
| `n_ofertas_ong`, `rodadas_ong`, `escalado_admin` | NUMERIC/bool | Quantas ofertas e rodadas até o aceite; se escalou para o Admin | desfecho |
| `orientado_refrigerar`, `refrigerado_apos_orientacao` | bool | Orientação de refrigeração (7.5) | desfecho |
| `ong_id`, `ts_aceite_ong`, `minutos_ate_match` | — | ONG que aceitou; tempo de match (KPI) | desfecho |
| `modalidade`, `transportador_id`, `hub_id` | texto | Como o lote foi transportado | desfecho |
| `rodadas_transporte` | NUMERIC | Rodadas até conseguir transporte | desfecho |
| `acionou_pago`, `custo_caixa`, `aprovacao_caixa`, `caixa_aprovado` | — | Uso do caixa solidário (9) | desfecho |
| `ts_coleta`, `ts_entrega`, `minutos_trajeto` | — | Tempos logísticos | desfecho |
| `minutos_espera_janela` | NUMERIC | Espera até a janela de recebimento da ONG abrir (6.4) | desfecho |
| `complementaridade` | texto | complementar, sem_transporte, redundante: par doador × ONG escolhido (6.6) | desfecho |
| `ong_tinha_pedido`, `pedido_atendido` | bool / texto | Se a ONG tinha pedido aberto da categoria e qual pedido a entrega abateu (6.5) | desfecho |
| `refeicoes` | NUMERIC | Refeições geradas (12.1), só para ENTREGUE | desfecho / KPI |
| `modo_logistico` | texto | v2.1: `direto` ou `via_hub` (impasse resolvido no ponto de encontro, 6.6) | desfecho |
| `excecao_redundante` | bool | v2.1: par redundante aceito por falta de alternativa (evento `EXCECAO_REDUNDANTE`) | desfecho |
| `minutos_espera_doador` | NUMERIC | v2.1: espera até a janela do doador abrir para a coleta (6.1) | desfecho |

---

## `eventos.csv.gz`: trilha de auditoria (regras, seção 10)

| Coluna | Descrição |
|---|---|
| `evento_id` | Identificador `E-0000001`, em ordem cronológica |
| `lote_id` | FK para `lotes.csv` |
| `ts` | Momento do evento |
| `tipo` | CADASTRO, BLOQUEIO_QUESTIONARIO, BLOQUEIO_VALIDADE, TRIAGEM, OFERTA_ONG, ACEITE_ONG, RECUSA_ONG, EXPIRACAO_ONG, ESCALADA_ADMIN, REALOCACAO_ADMIN, NOVA_RODADA_ONG, EXCECAO_REDUNDANTE, ORIENTACAO_REFRIGERAR, REFRIGERADO_PELO_DOADOR, OFERTA_TRANSPORTE, ACIONA_PAGO, APROVACAO_CAIXA, CAIXA_NEGADO, ACEITE_TRANSPORTE, COLETA, ENTREGA, RECUSA_INSPECAO, DESCARTE |
| `ator` | Quem agiu: `doador:D-…`, `ong:O-…`, `transportador:…`, `gestor_caixa`, `admin`, `triador`, `sistema` |
| `detalhe` | Contexto curto (prazo, distância, valor, motivo) |

---

## Entidades

**`doadores.csv`:** `doador_id`, `cd_setor` (setor censitário real), `regiao`, `municipio`, `ipvs_grupo` (1–6 do setor), `lat`/`lon`, `tipo_doador`, `segmento`, `tem_refrigeracao`, `pode_entregar` (capacidade, 6.6), `aceita_coleta` (v2.1: falso = "só entrega"), `abertura_h`/`fechamento_h` (v2.1: janela em que o lote pode sair), `documento_hash`.

**`ongs.csv`:** `ong_id`, `cd_setor`, `regiao`, `municipio`, `ipvs_grupo` (usado no ranking, regras 6.1), `lat`/`lon`, `status_aprovacao` (aprovada / pendente / reprovada), `capacidade_kg_dia`, `tem_refrigeracao`, `serve_refeicao`, `turnos` (`cafe|almoco|jantar|noturno`), `tem_cozinha`, `distribui_cestas`, `tem_freezer`, `pode_buscar` (veículo próprio), `aceita_receber_entrega` (v2.1: falso = "só busca"), `abertura_h`/`fechamento_h` (janela de recebimento), `categorias_aceitas` (separadas por `|`, dentro do que a estrutura comporta), `documento_hash`.

**`pedidos.csv`** (regras 6.5): `pedido_id`, `ong_id`, `categoria`, `kg`, `ts_abertura`, `ts_expira` (3 a 7 dias), `kg_atendido`, `status` (atendido, parcial, expirado).

**`hubs.csv`:** `hub_id`, `cd_setor`, `regiao`, `municipio`, `ipvs_grupo`, `lat`/`lon`, `tipo` (sede_ong, ceu, comercio_parceiro, estacionamento_conveniado), `validado_admin`.

**`transportadores.csv`:** `transportador_id` (V- voluntário, M- motorista de retorno, T- transportadora), `modalidade`, `veiculo` (moto, carro, van, caminhao), `refrigerado`, `capacidade_kg`, `regiao`/`municipio`/`lat`/`lon` (base), e para transportadoras a rota fixa A→B: `rota_b_regiao`, `rota_b_lat`, `rota_b_lon`.

**`contexto_diario.csv`:** `data`, `dia_semana`, `mes`, `feriado`, `chuva` (**latente**: afeta disponibilidade e velocidade, mas não é feature).

---

## Referências (`data/reference/`)

**`setores_rmsp.csv`:** saída de `src/data/curadoria_ipvs.py`. Colunas: `cd_setor`, `cd_mun`, `municipio`, `distrito`, `situacao`, `ipvs_grupo`, `ipvs_nome`, `lat`/`lon` (centroide do polígono), `subprefeitura`, `regiao`.

**`regioes.csv`:** `regiao`, `municipio`, `setores_classificados`, `setores_vulneraveis`, `ipvs_medio`, `lat`/`lon`, `pct_vulneravel` (% nos grupos 5–6), `indice_vulnerabilidade` (min-max 0–1).
