"""Matching de um lote NOVO (cadastrado pela API) com as ONGs cadastradas (regras 6.1 e 6.6).

Usa as MESMAS funções de `src/regras/logistica.py` que a simulação usa: filtros obrigatórios,
impasse busca × entrega, disponibilidade mútua, score e regra do par redundante. A diferença é
que aqui não há sorteio: o resultado é o ranking que o sistema ofereceria, na ordem, e as
features de contexto que o Modelo 2 precisa para estimar o risco de descarte.

Tempos são calculados no horário de Brasília sem fuso (como no dataset).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from src.data import parametros as P
from src.data.simulacao import distancia_km
from src.regras.dominio import Armazenamento, Categoria
from src.regras.logistica import (
    ATRASO_ESTIMADO_HUB,
    RAIO_DOADOR_ATE_HUB_KM,
    RAIO_MAXIMO_KM,
    ModoLogistico,
    PerfilOng,
    aplicar_regra_redundante,
    complementaridade,
    modo_logistico,
    motivo_incompatibilidade,
    score_ong,
    tempo_ate_receber,
    transporte_elegivel,
)

MIN = timedelta(minutes=1)


def minutos_trajeto(km: float, veiculo: str, quando: datetime) -> float:
    """Estimativa do sistema (sem chuva, que ele não conhece): igual à da simulação."""
    v = P.VELOCIDADE_KMH[veiculo]
    horas = quando.hour + quando.minute / 60
    if any(ini <= horas < fim for ini, fim in P.PICOS_TRANSITO):
        v *= P.TRANSITO_MULT_VELOCIDADE
    return km / v * 60


def turno_a_tempo(turnos: str, agora: datetime, limite: datetime) -> bool:
    if not isinstance(turnos, str) or not turnos:
        return False
    for offset in (0, 1):
        dia = datetime.combine(agora.date() + timedelta(days=offset), datetime.min.time())
        for turno in turnos.split("|"):
            ini, fim = P.ONG_TURNOS[turno]
            if dia + timedelta(hours=fim) > agora and max(dia + timedelta(hours=ini), agora) <= limite:
                return True
    return False


@dataclass(frozen=True)
class OngRanqueada:
    ong_id: str
    regiao: str
    score: float
    km: float
    minutos_ate_receber: float
    modo: str
    complementaridade: str


@dataclass(frozen=True)
class ResultadoMatching:
    ranking: list[OngRanqueada]
    excecao_redundante: bool
    n_ongs_impasse: int
    motivos_exclusao: dict[str, int]  # motivo -> quantas ONGs (vai para o log, regras 6.1)
    features_m2: dict


class Cadastro:
    """Doadores, ONGs, hubs e transportadores (em produção, vêm do banco; aqui, do dataset)."""

    def __init__(self, diretorio: Path):
        self.dir = diretorio

    @cached_property
    def doadores(self) -> pd.DataFrame:
        return pd.read_csv(self.dir / "doadores.csv").set_index("doador_id", drop=False)

    @cached_property
    def ongs(self) -> pd.DataFrame:
        o = pd.read_csv(self.dir / "ongs.csv")
        return o[o["status_aprovacao"] == "aprovada"].reset_index(drop=True)

    @cached_property
    def perfis(self) -> list[PerfilOng]:
        return [
            PerfilOng(
                categorias_aceitas=frozenset(Categoria(c) for c in str(o.categorias_aceitas).split("|") if c),
                tem_refrigeracao=bool(o.tem_refrigeracao), tem_freezer=bool(o.tem_freezer),
                tem_cozinha=bool(o.tem_cozinha), distribui_cestas=bool(o.distribui_cestas),
                pode_buscar=bool(o.pode_buscar), abertura_h=float(o.abertura_h), fechamento_h=float(o.fechamento_h),
                aceita_receber_entrega=bool(o.aceita_receber_entrega),
            )
            for o in self.ongs.itertuples()
        ]

    @cached_property
    def hubs(self) -> pd.DataFrame:
        return pd.read_csv(self.dir / "hubs.csv")

    @cached_property
    def transportadores(self) -> pd.DataFrame:
        return pd.read_csv(self.dir / "transportadores.csv")


def ranquear(cad: Cadastro, doador_id: str, categoria: Categoria, armazenamento: Armazenamento, peso_kg: float,
             requer_preparo: bool, rota_expressa: bool, validade: datetime, agora: datetime,
             disponivel_ate: datetime | None = None) -> ResultadoMatching:
    d = cad.doadores.loc[doador_id]
    o = cad.ongs
    dist = distancia_km(d.lat, d.lon, o["lat"].to_numpy(), o["lon"].to_numpy())
    limite = validade - timedelta(hours=P.MARGEM_CONSUMO_HORAS[categoria])
    janela_doador = (float(d.abertura_h), float(d.fechamento_h))

    dist_hubs = distancia_km(d.lat, d.lon, cad.hubs["lat"].to_numpy(), cad.hubs["lon"].to_numpy())
    i_hub = int(np.argmin(dist_hubs))
    hub = cad.hubs.iloc[i_hub]
    hub_viavel = bool(d.pode_entregar) and float(dist_hubs[i_hub]) <= RAIO_DOADOR_ATE_HUB_KM and not rota_expressa

    candidatos, motivos, n_impasse = [], {}, 0

    def excluir(motivo: str) -> None:
        motivos[motivo] = motivos.get(motivo, 0) + 1

    for i, ong in enumerate(o.itertuples()):
        perfil = cad.perfis[i]
        if dist[i] > RAIO_MAXIMO_KM:
            excluir("fora_do_raio")
            continue
        if (m := motivo_incompatibilidade(categoria, armazenamento, requer_preparo, perfil)) is not None:
            excluir(m)
            continue
        alcanca = bool(d.pode_entregar) and (dist[i] <= P.DOADOR_ENTREGA_DIST_MAX_KM or d.tipo_doador == "PF")
        modo = modo_logistico(alcanca, bool(d.aceita_coleta), perfil.pode_buscar, perfil.aceita_receber_entrega,
                              hub_viavel)
        if modo == ModoLogistico.IMPASSE:
            n_impasse += 1
            excluir("impasse_busca_entrega")
            continue
        if peso_kg > ong.capacidade_kg_dia:
            excluir("sem_capacidade")
            continue
        km = float(dist[i]) if modo == ModoLogistico.DIRETO else float(
            dist_hubs[i_hub] + distancia_km(hub.lat, hub.lon, ong.lat, ong.lon))
        trajeto = timedelta(minutes=minutos_trajeto(km, "carro", agora))
        if modo == ModoLogistico.VIA_HUB:
            trajeto += ATRASO_ESTIMADO_HUB
        ate_receber = tempo_ate_receber(agora, trajeto, perfil.abertura_h, perfil.fechamento_h,
                                        janela_doador=janela_doador)
        if agora + ate_receber > limite:
            excluir("nao_chega_a_tempo")
            continue
        if disponivel_ate is not None and agora + ate_receber - trajeto > disponivel_ate:
            excluir("doador_indisponivel")
            continue
        a_tempo = turno_a_tempo(ong.turnos, agora, limite)
        if rota_expressa and not (a_tempo and transporte_elegivel(
                categoria, armazenamento, False, timedelta(minutes=minutos_trajeto(km, "moto", agora)))):
            excluir("rota_expressa")
            continue
        comp = complementaridade(alcanca, perfil.pode_buscar)
        candidatos.append({
            "score": score_ong(ate_receber, 1.0, int(ong.ipvs_grupo), a_tempo, comp, False), "i": i, "km": km,
            "min": ate_receber / MIN, "modo": str(modo), "comp": str(comp),
        })

    candidatos, excecao = aplicar_regra_redundante(candidatos, lambda c: c["comp"])
    candidatos.sort(key=lambda c: c["score"], reverse=True)
    ranking = [OngRanqueada(str(o.iloc[c["i"]].ong_id), str(o.iloc[c["i"]].regiao), round(c["score"], 4),
                            round(c["km"], 2), round(c["min"], 1), c["modo"], c["comp"]) for c in candidatos]

    t = cad.transportadores
    d_t = distancia_km(d.lat, d.lon, t["lat"].to_numpy(), t["lon"].to_numpy())
    perto = d_t <= P.RAIO_TRANSPORTADOR_KM
    features = {
        "n_ongs_compativeis_10km": sum(1 for c in candidatos if c["km"] <= 10),
        "dist_ong_top_km": ranking[0].km if ranking else np.nan,
        "min_ate_receber_top": ranking[0].minutos_ate_receber if ranking else np.nan,
        "n_ongs_impasse": n_impasse,
        "n_transportadores_ativos_raio": int(perto.sum()),
        "refrigerado_disponivel": bool(t["refrigerado"].to_numpy()[perto].any()),
        "doador_tem_refrigeracao": bool(d.tem_refrigeracao),
        "doador_pode_entregar": bool(d.pode_entregar),
        "doador_aceita_coleta": bool(d.aceita_coleta),
    }
    return ResultadoMatching(ranking[:10], excecao, n_impasse, motivos, features)
