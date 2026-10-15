"""Tela do Transportador: corridas lidas do dataset e rota aberta no Google Maps sem chave."""

from urllib.parse import parse_qs, urlsplit

import pandas as pd

from src.dashboard import dados


def test_link_google_maps_monta_rota_sem_chave():
    url = dados.link_google_maps((-23.5, -46.6), (-23.6, -46.7))
    partes = urlsplit(url)
    q = parse_qs(partes.query)
    assert partes.netloc == "www.google.com" and partes.path == "/maps/dir/"
    assert q["api"] == ["1"] and q["travelmode"] == ["driving"]
    assert q["origin"] == ["-23.5,-46.6"] and q["destination"] == ["-23.6,-46.7"]
    assert "key" not in q


def test_corridas_so_do_transportador_com_coleta_e_entrega():
    c = dados.corridas_transportador("V-001")
    assert not c.empty
    assert set(c["transportador_id"]) == {"V-001"}
    for col in ("lote_id", "prioridade", "peso_kg", "status_final", "coleta_lat", "coleta_lon",
                "entrega_lat", "entrega_lon", "coleta_nome", "ong_id"):
        assert col in c.columns
    assert c[["coleta_lat", "coleta_lon", "entrega_lat", "entrega_lon"]].notna().all().all()


def test_corrida_via_hub_coleta_no_hub_e_nao_mostra_doador():
    l = pd.read_csv(dados.DADOS / "lotes.csv", low_memory=False,
                    usecols=["transportador_id", "hub_id", "modo_logistico"])
    via_hub = l[(l["modo_logistico"] == "via_hub") & l["hub_id"].notna() & l["transportador_id"].notna()]
    if via_hub.empty:
        return
    tid = via_hub["transportador_id"].iloc[0]
    c = dados.corridas_transportador(tid)
    hub = c[c["modo_logistico"] == "via_hub"]
    assert hub["coleta_nome"].str.startswith("Hub").all()
    assert "doador_id" not in c.columns  # minimização: o transportador vê o ponto de coleta, não o cadastro


def test_transportador_inexistente_volta_vazio():
    assert dados.corridas_transportador("V-999999").empty
