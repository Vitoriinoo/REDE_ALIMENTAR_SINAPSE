"""Aba Ao vivo: alerta vermelho/amarelo só para lote pendente, pela prioridade do Modelo 1."""

import pandas as pd

from src.dashboard.dados import alertas_ao_vivo


def test_alerta_so_para_pendente_critica_ou_alta():
    r = pd.DataFrame({
        "codigo": ["L1", "L2", "L3", "L4", "L5"],
        "prioridade": ["CRITICA", "ALTA", "CRITICA", "MEDIA", "BAIXA"],
        "status_final": ["PENDENTE", "PENDENTE", "ENTREGUE", "PENDENTE", "PENDENTE"],
    })
    tabela, niveis, n_critica, n_alta = alertas_ao_vivo(r)
    assert niveis == ["critico", "atencao", None, None, None]  # CRÍTICA já entregue não alerta
    assert (n_critica, n_alta) == (1, 1)
    assert tabela["prioridade"].tolist()[:2] == ["CRÍTICA", "ALTA"]


def test_tabela_vazia_e_prioridade_desconhecida_nao_quebram():
    vazio = pd.DataFrame(columns=["codigo", "prioridade", "status_final"])
    assert alertas_ao_vivo(vazio)[1:] == ([], 0, 0)
    tabela, niveis, *_ = alertas_ao_vivo(pd.DataFrame({"prioridade": [None], "status_final": ["PENDENTE"]}))
    assert niveis == [None] and tabela["prioridade"].isna().all()


def test_peso_numeric_do_banco_aparece_como_numero():
    from decimal import Decimal

    r = pd.DataFrame({"prioridade": ["BAIXA"], "status_final": ["PENDENTE"], "peso_kg": [Decimal("9.500000")]})
    peso = alertas_ao_vivo(r)[0]["peso_kg"]
    assert peso.dtype == "float64" and peso.tolist() == [9.5]  # Decimal == 9.5 também é True: checar o tipo


def test_mediana_geral_e_de_todos_os_matches_nao_das_prioridades():
    from src.dashboard import dados

    geral = dados.match_geral() if not dados.URL else None
    if geral is None:
        return  # com banco configurado, quem calcula é a visão rede.vw_match_geral
    l = pd.read_csv(dados.DADOS / "lotes.csv", usecols=["minutos_ate_match"])["minutos_ate_match"].dropna()
    assert geral["mediana_min"] == l.median() and round(geral["mediana_min"], 1) == 26.4
