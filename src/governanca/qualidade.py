"""Checagens de qualidade de dados (governança de dados, regras seção 11).

Roda antes do treino e no pipeline de CI: dado ruim não vira modelo. Cada checagem
devolve quantas linhas violam a regra; qualquer violação faz o comando sair com erro.

Uso:
    python -m src.governanca.qualidade
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from src.data.curadoria_ipvs import RAIZ
from src.regras.dominio import Armazenamento, Categoria
from src.seguranca.minimizacao import _PADROES
from src.validacao.esquemas import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN

DIR = RAIZ / "data" / "processed"
SAIDA = RAIZ / "reports" / "qualidade_dados.json"


def _checar(nome: str, violacoes: int, total: int) -> dict:
    return {"checagem": nome, "violacoes": int(violacoes), "total": int(total), "ok": bool(violacoes == 0)}


def checar() -> list[dict]:
    lotes = pd.read_csv(DIR / "lotes.csv", low_memory=False)
    doadores = pd.read_csv(DIR / "doadores.csv")
    ongs = pd.read_csv(DIR / "ongs.csv")
    pedidos = pd.read_csv(DIR / "pedidos.csv")
    n = len(lotes)
    validos = lotes[lotes["status_final"] != "BLOQUEADO"]
    r = []

    # Unicidade e integridade referencial
    r.append(_checar("lote_id único", lotes["lote_id"].duplicated().sum(), n))
    r.append(_checar("lote aponta para doador existente", (~lotes["doador_id"].isin(doadores["doador_id"])).sum(), n))
    r.append(_checar("lote aponta para ONG existente",
                     (lotes["ong_id"].notna() & ~lotes["ong_id"].isin(ongs["ong_id"])).sum(), n))
    r.append(_checar("pedido aponta para ONG existente", (~pedidos["ong_id"].isin(ongs["ong_id"])).sum(), len(pedidos)))

    # Domínio e faixas (as mesmas da validação de entrada, regras 4.6)
    r.append(_checar("categoria na lista fechada", (~lotes["categoria"].isin([c.value for c in Categoria])).sum(), n))
    r.append(_checar("armazenamento na lista fechada",
                     (~lotes["armazenamento"].isin([a.value for a in Armazenamento])).sum(), n))
    r.append(_checar("peso entre 0,5 e 10.000 kg", (~lotes["peso_kg"].between(0.5, 10_000)).sum(), n))
    r.append(_checar("validade efetiva preenchida", lotes["validade_efetiva"].isna().sum(), n))
    for nome, df in (("doadores", doadores), ("ongs", ongs)):
        fora = ~(df["lat"].between(LAT_MIN, LAT_MAX) & df["lon"].between(LON_MIN, LON_MAX))
        r.append(_checar(f"{nome} dentro do recorte geográfico", fora.sum(), len(df)))

    # Regras de negócio como invariantes do dado
    pf = lotes[lotes["tipo_doador"] == "PF"]
    r.append(_checar("PF só doa não perecível (regras 4.1)", (pf["categoria"] != "nao_perecivel").sum(), len(pf)))
    r.append(_checar("lote válido tem prioridade", validos["prioridade"].isna().sum(), len(validos)))
    r.append(_checar("ONG pendente/reprovada nunca recebe lote",
                     lotes["ong_id"].isin(ongs.loc[ongs["status_aprovacao"] != "aprovada", "ong_id"]).sum(), n))
    entregues = lotes[lotes["status_final"] == "ENTREGUE"]
    r.append(_checar("entrega acontece depois do cadastro",
                     (pd.to_datetime(entregues["ts_entrega"]) < pd.to_datetime(entregues["ts_cadastro"])).sum(),
                     len(entregues)))

    # Minimização: nenhum dado pessoal em texto livre do dataset
    textos = lotes["descricao_texto"].fillna("")
    com_pii = textos.apply(lambda t: any(p.search(t) for _, p in _PADROES))
    r.append(_checar("texto livre sem CPF/CNPJ/e-mail/telefone", com_pii.sum(), n))
    return r


def main() -> int:
    resultado = checar()
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in resultado:
        print(f"[{'OK' if c['ok'] else 'FALHA'}] {c['checagem']}: {c['violacoes']}/{c['total']}")
    return 0 if all(c["ok"] for c in resultado) else 1


if __name__ == "__main__":
    sys.exit(main())
