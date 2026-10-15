"""Tela da ONG: aceitar e confirmar a entrega chamam a API e a página não quebra depois do clique."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.dashboard import cliente_api  # noqa: E402

LOTE = {"codigo": "L-API-X", "categoria": "preparado", "armazenamento": "refrigerado", "peso_kg": 7.0,
        "prioridade": "BAIXA", "validade_efetiva": "2026-10-18T10:00:00Z", "regiao_doador": "SP - Centro", "km": 5.0,
        "minutos_ate_receber": 30.0, "modo": "direto", "ts_cadastro": "2026-10-15T10:20:12Z",
        "ts_aceite_ong": None, "refeicoes_estimadas": 16.7}
PERFIL = {"ong_id": "O-023", "regiao": "SP - Norte 1", "municipio": "São Paulo", "ipvs_grupo": 6, "lat": -23.47,
          "lon": -46.6, "status_aprovacao": "aprovada", "capacidade_kg_dia": 80.0, "tem_cozinha": True,
          "tem_refrigeracao": True, "tem_freezer": True, "distribui_cestas": False, "serve_refeicao": True,
          "pode_buscar": True, "aceita_receber_entrega": True, "abertura_h": 13.0, "fechamento_h": 23.0,
          "turnos": ["almoco"], "categorias_aceitas": ["preparado"]}


def _tela(monkeypatch, ofertas, aguardando):
    chamadas = []

    def falso(metodo, rota, chave=None, corpo=None, bruto=False):
        chamadas.append((metodo, rota, corpo))
        if metodo == "POST":
            return {"status": "ENTREGUE", "refeicoes": 16.67, "minutos_ate_match": 4.1, "proxima_ong": "O-005"}
        return {"/v1/ong/ofertas": {"ofertas": ofertas, "aguardando_entrega": aguardando},
                "/v1/ong/historico": [], "/v1/ong/perfil": PERFIL}.get(rota, {})

    monkeypatch.setattr(cliente_api, "chamar", falso)
    at = AppTest.from_file("../src/dashboard/paginas/ong.py", default_timeout=60)
    at.session_state["ident"] = {"papel": "ong", "id": "O-023"}
    at.session_state["chave"] = "x"
    return at.run(), chamadas


@pytest.mark.parametrize("botao, rota", [("Aceitar", "/v1/lotes/L-API-X/aceite"),
                                         ("Confirmar entrega", "/v1/lotes/L-API-X/entrega")])
def test_clique_chama_a_api_e_a_pagina_continua_de_pe(monkeypatch, botao, rota):
    aceito = LOTE | {"ts_aceite_ong": "2026-10-15T10:24:00Z"}
    at, chamadas = _tela(monkeypatch, [LOTE] if botao == "Aceitar" else [], [aceito] if botao != "Aceitar" else [])
    next(b for b in at.button if b.label == botao).click().run()
    assert ("POST", rota) in [(m, r) for m, r, _ in chamadas]
    assert not at.exception, [e.value for e in at.exception]
    assert at.success  # a mensagem sobrevive ao st.rerun()
