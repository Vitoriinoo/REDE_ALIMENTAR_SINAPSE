"""Entidades da rede (doadores, ONGs, hubs, transportadores) posicionadas em setores censitários reais."""

from __future__ import annotations

import hashlib
import hmac
import os

import numpy as np
import pandas as pd

from src.data import parametros as P
from src.data.curadoria_ipvs import DIR_REF
from src.regras.logistica import categorias_suportadas

GRAUS_POR_METRO = 1 / 111_000


def carregar_setores() -> pd.DataFrame:
    setores = pd.read_csv(DIR_REF / "setores_rmsp.csv", dtype={"cd_setor": str, "cd_mun": str})
    return setores[(setores["situacao"] == "Urbana") & setores["ipvs_grupo"].notna()].reset_index(drop=True)


def carregar_regioes() -> pd.DataFrame:
    return pd.read_csv(DIR_REF / "regioes.csv")


def _hash_documento(identificador: str) -> str:
    """HMAC-SHA256 do documento (regras, seção 11): sem a chave, o hash não é revertível por força bruta.

    Em produção a chave vem do cofre de segredos. Aqui os documentos são sintéticos,
    então existe um valor padrão só para o gerador funcionar sem configuração.
    """
    chave = os.environ.get("REDE_ALIMENTA_CHAVE_HMAC", "somente-dados-sinteticos").encode()
    return hmac.new(chave, identificador.encode(), hashlib.sha256).hexdigest()


def _sortear_setores(rng: np.random.Generator, setores: pd.DataFrame, pesos: dict[int, float], n: int) -> pd.DataFrame:
    w = setores["ipvs_grupo"].map(pesos).to_numpy(dtype=float)
    idx = rng.choice(len(setores), size=n, p=w / w.sum())
    return setores.iloc[idx].reset_index(drop=True)


def _posicionar(rng: np.random.Generator, base: pd.DataFrame, jitter_m: float) -> pd.DataFrame:
    out = base[["cd_setor", "regiao", "municipio", "ipvs_grupo"]].copy()
    out["ipvs_grupo"] = out["ipvs_grupo"].astype(int)
    out["lat"] = (base["lat"] + rng.normal(0, jitter_m * GRAUS_POR_METRO, len(base))).round(6)
    out["lon"] = (base["lon"] + rng.normal(0, jitter_m * GRAUS_POR_METRO, len(base))).round(6)
    return out


def gerar_doadores(rng: np.random.Generator, setores: pd.DataFrame) -> pd.DataFrame:
    prob_refrigeracao = {"restaurante": 0.9, "mercado": 0.95, "padaria": 0.7, "hortifruti": 0.3, "industria": 0.95}
    partes = []
    for segmento, n in P.DOADORES_PJ_POR_SEGMENTO.items():
        df = _posicionar(rng, _sortear_setores(rng, setores, P.PESO_SETOR_DOADOR_PJ, n), jitter_m=120)
        df["tipo_doador"], df["segmento"] = "PJ", segmento
        df["tem_refrigeracao"] = rng.random(n) < prob_refrigeracao[segmento]
        partes.append(df)
    # PF fica no centroide exato do setor: nunca expomos o endereço (regras, seção 11).
    pf = _posicionar(rng, _sortear_setores(rng, setores, P.PESO_SETOR_DOADOR_PF, P.N_DOADORES_PF), jitter_m=0)
    pf["tipo_doador"], pf["segmento"], pf["tem_refrigeracao"] = "PF", "pf", False
    partes.append(pf)

    doadores = pd.concat(partes, ignore_index=True)
    doadores.insert(0, "doador_id", [f"D-{i:04d}" for i in range(1, len(doadores) + 1)])
    # v2.0: o doador declara se pode entregar (regras 6.6).
    doadores["pode_entregar"] = rng.random(len(doadores)) < doadores["segmento"].map(P.DOADOR_PROB_PODE_ENTREGAR)
    # Heterogeneidade: alguns doadores doam bem mais que outros.
    # Lognormal com média 1 (mu = -sigma²/2) para não inflar o volume total.
    doadores["fator_frequencia"] = rng.lognormal(-0.5**2 / 2, 0.5, len(doadores)).round(3)
    doadores["documento_hash"] = doadores["doador_id"].map(_hash_documento)
    return doadores


def gerar_ongs(rng: np.random.Generator, setores: pd.DataFrame) -> pd.DataFrame:
    n = P.N_ONGS
    ongs = _posicionar(rng, _sortear_setores(rng, setores, P.PESO_SETOR_ONG, n), jitter_m=120)
    ongs.insert(0, "ong_id", [f"O-{i:03d}" for i in range(1, n + 1)])

    status = ["aprovada"] * (n - P.ONGS_PENDENTES - P.ONGS_REPROVADAS)
    status += ["pendente"] * P.ONGS_PENDENTES + ["reprovada"] * P.ONGS_REPROVADAS
    ongs["status_aprovacao"] = rng.permutation(status)

    ongs["capacidade_kg_dia"] = np.clip(
        rng.lognormal(np.log(P.ONG_CAPACIDADE_MEDIANA_KG), P.ONG_CAPACIDADE_SIGMA, n), 20, 400
    ).round(0)
    ongs["tem_refrigeracao"] = rng.random(n) < P.ONG_PROB_REFRIGERACAO
    ongs["serve_refeicao"] = rng.random(n) < P.ONG_PROB_SERVE_REFEICAO

    turnos = []
    for serve in ongs["serve_refeicao"]:
        escolhidos = [t for t, p in P.ONG_PROB_TURNO.items() if serve and rng.random() < p]
        if serve and not escolhidos:
            escolhidos = ["almoco"]
        turnos.append("|".join(escolhidos))
    ongs["turnos"] = turnos

    # v2.0: capacidades declaradas, janela de recebimento e categorias aceitas (regras 6.4).
    serve = ongs["serve_refeicao"].to_numpy()
    ongs["tem_cozinha"] = rng.random(n) < np.where(serve, P.ONG_PROB_COZINHA[True], P.ONG_PROB_COZINHA[False])
    ongs["distribui_cestas"] = rng.random(n) < np.where(serve, P.ONG_PROB_CESTAS[True], P.ONG_PROB_CESTAS[False])
    ongs["tem_freezer"] = ongs["tem_refrigeracao"] & (rng.random(n) < P.ONG_PROB_FREEZER_SE_REFRIGERACAO)
    ongs["pode_buscar"] = rng.random(n) < P.ONG_PROB_VEICULO
    janelas, pesos = zip(*P.ONG_JANELAS)
    escolhidas = [janelas[i] for i in rng.choice(len(janelas), size=n, p=np.array(pesos) / sum(pesos))]
    ongs["abertura_h"] = [float(j[0]) for j in escolhidas]
    ongs["fechamento_h"] = [float(P.ONG_FECHAMENTO_NOTURNO if "noturno" in t else j[1])
                            for j, t in zip(escolhidas, ongs["turnos"])]
    aceitas = []
    for ong in ongs.itertuples():
        suportadas = sorted(categorias_suportadas(bool(ong.tem_refrigeracao), bool(ong.tem_freezer)))
        lista = [c for c in suportadas if rng.random() >= P.ONG_PROB_RECUSAR_CATEGORIA] or suportadas
        aceitas.append("|".join(lista))
    ongs["categorias_aceitas"] = aceitas
    ongs["documento_hash"] = ongs["ong_id"].map(_hash_documento)
    return ongs


def gerar_hubs(rng: np.random.Generator, setores: pd.DataFrame) -> pd.DataFrame:
    # Ao menos 1 hub por região; o restante segue a vulnerabilidade (mais pontos onde há ONGs).
    base = [setores[setores["regiao"] == r].sample(1, random_state=int(rng.integers(1e9))) for r in sorted(setores["regiao"].unique())]
    restantes = P.N_HUBS - len(base)
    base.append(_sortear_setores(rng, setores, P.PESO_SETOR_HUB, restantes))
    hubs = _posicionar(rng, pd.concat(base, ignore_index=True), jitter_m=80)
    hubs.insert(0, "hub_id", [f"H-{i:02d}" for i in range(1, len(hubs) + 1)])
    hubs["tipo"] = rng.choice(
        ["sede_ong", "ceu", "comercio_parceiro", "estacionamento_conveniado"], len(hubs), p=[0.35, 0.25, 0.25, 0.15]
    )
    hubs["validado_admin"] = True
    return hubs


def gerar_transportadores(rng: np.random.Generator, setores: pd.DataFrame, regioes: pd.DataFrame) -> pd.DataFrame:
    uniforme = {g: 1.0 for g in range(1, 7)}

    vol = _posicionar(rng, _sortear_setores(rng, setores, uniforme, P.N_VOLUNTARIOS), jitter_m=150)
    vol["transportador_id"] = [f"V-{i:03d}" for i in range(1, len(vol) + 1)]
    vol["modalidade"] = "voluntario"
    vol["veiculo"] = rng.choice(["carro", "moto"], len(vol), p=[0.6, 0.4])
    vol["refrigerado"] = False

    mot = _posicionar(rng, _sortear_setores(rng, setores, uniforme, P.N_MOTORISTAS_RETORNO), jitter_m=150)
    mot["transportador_id"] = [f"M-{i:03d}" for i in range(1, len(mot) + 1)]
    mot["modalidade"] = "motorista_retorno"
    mot["veiculo"] = rng.choice(["van", "carro", "caminhao"], len(mot), p=[0.5, 0.3, 0.2])
    mot["refrigerado"] = rng.random(len(mot)) < P.MOTORISTA_PROB_REFRIGERADO

    # Transportadoras: rota fixa A -> B entre duas regiões distintas (voltam vazias de B para A).
    n = P.N_TRANSPORTADORAS
    pares = [rng.choice(len(regioes), size=2, replace=False) for _ in range(n)]
    a = regioes.iloc[[p[0] for p in pares]].reset_index(drop=True)
    b = regioes.iloc[[p[1] for p in pares]].reset_index(drop=True)
    jit = lambda: rng.normal(0, 800 * GRAUS_POR_METRO, n)  # noqa: E731
    tra = pd.DataFrame({
        "transportador_id": [f"T-{i:03d}" for i in range(1, n + 1)],
        "modalidade": "transportadora",
        "veiculo": rng.choice(["caminhao", "van"], n, p=[0.6, 0.4]),
        "refrigerado": rng.random(n) < P.TRANSPORTADORA_PROB_REFRIGERADA,
        "regiao": a["regiao"], "municipio": a["municipio"],
        "lat": (a["lat"] + jit()).round(6), "lon": (a["lon"] + jit()).round(6),
        "rota_b_regiao": b["regiao"],
        "rota_b_lat": (b["lat"] + jit()).round(6), "rota_b_lon": (b["lon"] + jit()).round(6),
    })

    capacidade = {"moto": 30, "carro": 150, "van": 800, "caminhao": 3000}
    todos = pd.concat([vol, mot, tra], ignore_index=True)
    todos["capacidade_kg"] = todos["veiculo"].map(capacidade)
    colunas = ["transportador_id", "modalidade", "veiculo", "refrigerado", "capacidade_kg", "regiao", "municipio",
               "lat", "lon", "rota_b_regiao", "rota_b_lat", "rota_b_lon"]
    return todos[colunas]
