# Dicionário de Dados: Rede Alimenta IA

> Dataset **simulado e calibrado com fontes públicas** (IPVS 2022/SEADE, TACO/UNICAMP, PAT, WRAP), 12 meses (set/2025–ago/2026).
> Reprodutível: `python -m src.data.curadoria_ipvs` e depois `python -m src.data.gerar_dataset` (semente 42).
> Premissas da simulação: `src/data/parametros.py` e regras, seção 8.1.

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
| `data/processed/lotes.csv` | 25.939 | 1 doação cadastrada |
| `data/processed/eventos.csv.gz` | ~245 mil | 1 evento da trilha de auditoria |
| `data/processed/doadores.csv` | 300 | 1 doador (210 PJ, 90 PF) |
| `data/processed/ongs.csv` | 60 | 1 ONG (55 aprovadas, 3 pendentes, 2 reprovadas) |
| `data/processed/hubs.csv` | 40 | 1 ponto de encontro validado |
| `data/processed/transportadores.csv` | 160 | 1 transportador (70 voluntários, 65 motoristas de retorno, 25 transportadoras) |
| `data/processed/contexto_diario.csv` | 365 | 1 dia |
| `data/reference/setores_rmsp.csv` | 36.847 | 1 setor censitário real (IPVS 2022) |
| `data/reference/regioes.csv` | 15 | 1 região (8 macrorregiões de SP + 7 municípios) |

**Privacidade (LGPD):** não há nome, CPF, CNPJ, telefone ou endereço em nenhum arquivo. Documentos existem só como `documento_hash` (SHA-256). Doadores PF ficam no **centroide do setor censitário**, nunca no endereço.

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

### Cadastro (informado pelo doador ou calculado pelo sistema)
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `ts_cadastro` | datetime | Momento do cadastro (horário de Brasília) | — (usada no split temporal) |
| `categoria` | texto | preparado, refrigerado, congelado, hortifruti, padaria, nao_perecivel | M1, M2 |
| `armazenamento` | texto | refrigerado, congelado, ambiente | M1, M2 |
| `peso_kg` | float | Peso do lote | M1, M2 |
| `descricao_texto` | texto | Descrição livre (entrada do NLP zero-shot) | NLP |
| `texto_adversarial` | bool | Descrição é um payload de ataque (~1,5%) | avaliação do guardrail |
| `tipo_adversarial` | texto | prompt_injection, entrada_gigante, html_script, sql_injection | avaliação do guardrail |
| `ts_preparo` | datetime | Hora do preparo (só Preparado) | — |
| `validade_rotulo` | datetime | Validade do rótulo (Refrigerado/Congelado) | — |
| `ts_saida_refrigeracao` | datetime | Desde quando está fora da refrigeração | — |
| `validade_informada` | datetime | Validade informada (Hortifruti, Padaria, Não perecível) | — |
| `validade_efetiva` | datetime | **Calculada pelo sistema** (regras 4.2) | — |
| `horas_restantes` | float | `validade_efetiva − ts_cadastro`, em horas | M1, M2 |
| `rota_expressa` | bool | Cadeia fria fora da refrigeração (regras 7.5) | M1, M2 |

### Triagem
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `prioridade` | texto | CRITICA, ALTA, MEDIA, BAIXA: **rótulo do triador humano** (regra + ~9% de discordância) | **alvo M1**; M2 (no teste, usa a predição do M1) |
| `prioridade_regra` | texto | Prioridade pela regra determinística (5.1), sem ruído | baseline, **proibida como feature** |
| `prioridade_operacional` | texto | Nova prioridade após o doador refrigerar (7.5) | desfecho |

### Contexto no momento da decisão
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `hora`, `dia_semana` | int | Hora (0–23) e dia (0 = segunda) do cadastro | M2 |
| `mes` | int | Mês do cadastro | — (fora do M2: split temporal) |
| `fim_de_semana`, `feriado` | bool | Calendário | M2 |
| `n_ongs_compativeis_10km` | int | ONGs elegíveis (aprovadas, com capacidade e compatíveis) num raio de 10 km | M2 |
| `dist_ong_top_km` | float | Distância viária até a ONG mais bem ranqueada (vazio se nenhuma) | M2 |
| `n_transportadores_ativos_raio` | int | Transportadores ativos no dia num raio de 12 km | M2 |
| `refrigerado_disponivel` | bool | Há veículo refrigerado ativo no raio | M2 |

### Desfecho (proibido como feature)
| Coluna | Tipo | Descrição | Uso |
|---|---|---|---|
| `status_final` | texto | ENTREGUE, DESCARTADO, BLOQUEADO | desfecho |
| `descartado` | bool | Lote perdido (vazio para BLOQUEADO) | **alvo M2** |
| `motivo_descarte` | texto | SEM_ONG_ELEGIVEL, NENHUMA_ONG_ACEITOU, SEM_TRANSPORTE, QUEBRA_CADEIA_FRIA, VENCEU_ANTES_DA_ENTREGA, VENCEU_AGUARDANDO_ONG, RECUSADO_NA_INSPECAO, REFRIGERADO_FORA_DA_JANELA, VALIDADE_ABAIXO_DO_MINIMO | desfecho |
| `n_ofertas_ong`, `rodadas_ong`, `escalado_admin` | int/bool | Quantas ofertas e rodadas até o aceite; se escalou para o Admin | desfecho |
| `orientado_refrigerar`, `refrigerado_apos_orientacao` | bool | Orientação de refrigeração (7.5) | desfecho |
| `ong_id`, `ts_aceite_ong`, `minutos_ate_match` | — | ONG que aceitou; tempo de match (KPI) | desfecho |
| `modalidade`, `transportador_id`, `hub_id` | texto | Como o lote foi transportado | desfecho |
| `rodadas_transporte` | int | Rodadas até conseguir transporte | desfecho |
| `acionou_pago`, `custo_caixa`, `aprovacao_caixa`, `caixa_aprovado` | — | Uso do caixa solidário (9) | desfecho |
| `ts_coleta`, `ts_entrega`, `minutos_trajeto` | — | Tempos logísticos | desfecho |
| `refeicoes` | float | Refeições geradas (12.1), só para ENTREGUE | desfecho / KPI |

---

## `eventos.csv.gz`: trilha de auditoria (regras, seção 10)

| Coluna | Descrição |
|---|---|
| `evento_id` | Identificador `E-0000001`, em ordem cronológica |
| `lote_id` | FK para `lotes.csv` |
| `ts` | Momento do evento |
| `tipo` | CADASTRO, BLOQUEIO_VALIDADE, TRIAGEM, OFERTA_ONG, ACEITE_ONG, RECUSA_ONG, EXPIRACAO_ONG, ESCALADA_ADMIN, REALOCACAO_ADMIN, NOVA_RODADA_ONG, ORIENTACAO_REFRIGERAR, REFRIGERADO_PELO_DOADOR, OFERTA_TRANSPORTE, ACIONA_PAGO, APROVACAO_CAIXA, CAIXA_NEGADO, ACEITE_TRANSPORTE, COLETA, ENTREGA, RECUSA_INSPECAO, DESCARTE |
| `ator` | Quem agiu: `doador:D-…`, `ong:O-…`, `transportador:…`, `gestor_caixa`, `admin`, `triador`, `sistema` |
| `detalhe` | Contexto curto (prazo, distância, valor, motivo) |

---

## Entidades

**`doadores.csv`:** `doador_id`, `cd_setor` (setor censitário real), `regiao`, `municipio`, `ipvs_grupo` (1–6 do setor), `lat`/`lon`, `tipo_doador`, `segmento`, `tem_refrigeracao`, `documento_hash`.

**`ongs.csv`:** `ong_id`, `cd_setor`, `regiao`, `municipio`, `ipvs_grupo` (usado no ranking, regras 6.1), `lat`/`lon`, `status_aprovacao` (aprovada / pendente / reprovada), `capacidade_kg_dia`, `tem_refrigeracao`, `serve_refeicao`, `turnos` (`cafe|almoco|jantar|noturno`), `documento_hash`.

**`hubs.csv`:** `hub_id`, `cd_setor`, `regiao`, `municipio`, `ipvs_grupo`, `lat`/`lon`, `tipo` (sede_ong, ceu, comercio_parceiro, estacionamento_conveniado), `validado_admin`.

**`transportadores.csv`:** `transportador_id` (V- voluntário, M- motorista de retorno, T- transportadora), `modalidade`, `veiculo` (moto, carro, van, caminhao), `refrigerado`, `capacidade_kg`, `regiao`/`municipio`/`lat`/`lon` (base), e para transportadoras a rota fixa A→B: `rota_b_regiao`, `rota_b_lat`, `rota_b_lon`.

**`contexto_diario.csv`:** `data`, `dia_semana`, `mes`, `feriado`, `chuva` (**latente**: afeta disponibilidade e velocidade, mas não é feature).

---

## Referências (`data/reference/`)

**`setores_rmsp.csv`:** saída de `src/data/curadoria_ipvs.py`. Colunas: `cd_setor`, `cd_mun`, `municipio`, `distrito`, `situacao`, `ipvs_grupo`, `ipvs_nome`, `lat`/`lon` (centroide do polígono), `subprefeitura`, `regiao`.

**`regioes.csv`:** `regiao`, `municipio`, `setores_classificados`, `setores_vulneraveis`, `ipvs_medio`, `lat`/`lon`, `pct_vulneravel` (% nos grupos 5–6), `indice_vulnerabilidade` (min-max 0–1).
