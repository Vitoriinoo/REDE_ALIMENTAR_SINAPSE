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
    assert tabela["prioridade"].tolist()[:2] == ["🔴 CRÍTICA", "🟠 ALTA"]


def test_tabela_vazia_e_prioridade_desconhecida_nao_quebram():
    vazio = pd.DataFrame(columns=["codigo", "prioridade", "status_final"])
    assert alertas_ao_vivo(vazio)[1:] == ([], 0, 0)
    tabela, niveis, *_ = alertas_ao_vivo(pd.DataFrame({"prioridade": [None], "status_final": ["PENDENTE"]}))
    assert niveis == [None] and tabela["prioridade"].isna().all()
