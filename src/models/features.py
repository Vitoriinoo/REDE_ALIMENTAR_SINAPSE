"""Definição explícita das features de cada modelo (controle de vazamento de dados).

Regra: só entra como feature o que é CONHECIDO NO MOMENTO DA DECISÃO. Colunas de
desfecho (ONG que aceitou, modalidade, horários de coleta/entrega...) e fatores
latentes (chuva, qualidade) nunca entram.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.data.curadoria_ipvs import RAIZ

ARQUIVO_LOTES = RAIZ / "data" / "processed" / "lotes.csv"

# Split temporal: treina no passado, testa no futuro (regras, decisão de metodologia).
INICIO_TESTE = date(2026, 6, 1)  # jun-ago/2026 = teste
INICIO_VALIDACAO = date(2026, 3, 1)  # mar-mai/2026 = validação (seleção de modelo e threshold)

# --- Modelo 1: prioridade no cadastro (só o que o doador informa) ---------------------------
M1_CATEGORICAS = ["categoria", "armazenamento", "tipo_doador"]
M1_NUMERICAS = ["horas_restantes", "peso_kg"]
M1_BOOLEANAS = ["rota_expressa"]
M1_ALVO = "prioridade"

# --- Modelo 2: risco de descarte, com o contexto logístico do momento -------------------
# "prioridade" aqui é a SAÍDA do Modelo 1 (no teste, usamos a predição do M1, não o rótulo).
# "mes" fica de fora: com split temporal, os meses do teste nunca aparecem no treino.
M2_CATEGORICAS = ["categoria", "armazenamento", "tipo_doador", "segmento", "regiao", "prioridade"]
M2_NUMERICAS = [
    "horas_restantes", "peso_kg", "hora", "dia_semana",
    "n_ongs_compativeis_10km", "dist_ong_top_km", "n_transportadores_ativos_raio",
    "min_ate_receber_top",  # v2.0: trajeto + espera da janela da ONG mais bem ranqueada
]
M2_BOOLEANAS = [
    "rota_expressa", "doador_tem_refrigeracao", "fim_de_semana", "feriado", "refrigerado_disponivel",
    "doador_pode_entregar", "requer_preparo",  # v2.0: declarados no cadastro / questionário
]
M2_ALVO = "descartado"

# Colunas que NUNCA podem ser feature (desfecho ou latente). Checadas no treino.
PROIBIDAS = {
    "status_final", "motivo_descarte", "ong_id", "ts_aceite_ong", "minutos_ate_match", "n_ofertas_ong",
    "escalado_admin", "rodadas_ong", "rodadas_transporte", "modalidade", "transportador_id", "hub_id",
    "acionou_pago", "custo_caixa", "aprovacao_caixa", "caixa_aprovado", "ts_coleta", "ts_entrega",
    "minutos_trajeto", "refeicoes", "orientado_refrigerar", "refrigerado_apos_orientacao",
    "prioridade_operacional", "chuva", "prioridade_regra",
    # v2.0: desfecho do matching/entrega
    "complementaridade", "ong_tinha_pedido", "minutos_espera_janela", "pedido_atendido",
}


def carregar_lotes_validos() -> pd.DataFrame:
    lotes = pd.read_csv(ARQUIVO_LOTES, parse_dates=["ts_cadastro"], low_memory=False)
    validos = lotes[lotes["status_final"] != "BLOQUEADO"].copy()
    for col in set(M1_BOOLEANAS + M2_BOOLEANAS):
        validos[col] = validos[col].astype(bool)
    validos[M2_ALVO] = validos[M2_ALVO].astype(bool)
    return validos.sort_values("ts_cadastro").reset_index(drop=True)


def split_temporal(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(treino_ajuste, validação, teste). Treino completo = treino_ajuste + validação."""
    dia = df["ts_cadastro"].dt.date
    ajuste = df[dia < INICIO_VALIDACAO]
    validacao = df[(dia >= INICIO_VALIDACAO) & (dia < INICIO_TESTE)]
    teste = df[dia >= INICIO_TESTE]
    return ajuste, validacao, teste


def checar_vazamento(colunas: list[str]) -> None:
    vazadas = PROIBIDAS.intersection(colunas)
    if vazadas:
        raise ValueError(f"Colunas de desfecho/latentes usadas como feature: {sorted(vazadas)}")
