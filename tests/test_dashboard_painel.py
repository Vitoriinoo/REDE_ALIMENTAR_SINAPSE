"""Testes do painel de impacto com AppTest e validacao do resumo para a banca."""

from pathlib import Path
import unicodedata
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.dashboard import dados  # noqa: E402


def test_dados_resumo_banca_valores_oficiais():
    resumo = dados.resumo_banca()
    assert "kg_salvos" in resumo and resumo["kg_salvos"] > 300_000
    assert "refeicoes" in resumo and resumo["refeicoes"] > 900_000
    assert round(resumo["acuracia_ia"], 4) == 0.9195
    assert round(resumo["tempo_tipico_min"], 1) == 26.4
    assert resumo["vulnerabilidades_mitigadas"] == 22


def test_painel_apptest_executa_sem_excecao():
    caminho = Path(__file__).resolve().parents[1] / "src" / "dashboard" / "paginas" / "painel.py"
    at = AppTest.from_file(str(caminho), default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]

    # Verifica presenca do resumo da banca e dos entregaveis
    textos = [m.value for m in at.markdown]
    for exp in at.expander:
        textos.append(exp.label)
        textos.extend(m.value for m in exp.markdown)
    for sh in at.subheader:
        textos.append(sh.value)
    for cap in at.caption:
        textos.append(cap.value)

    texto_geral = "\n".join(textos)
    assert "Resumo para a banca" in texto_geral
    assert "Alimentos salvos" in texto_geral
    assert "Refeições geradas" in texto_geral
    assert "Acurácia da IA" in texto_geral
    assert "Tempo típico de match" in texto_geral
    assert "Vulnerabilidades mitigadas" in texto_geral
    assert "Entregáveis do projeto" in texto_geral
    assert "https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE" in texto_geral

    # Verifica ausencia de emojis em toda a pagina
    emojis = [c for c in texto_geral if unicodedata.category(c) in ("So", "Sk") or ord(c) > 0x1F000]
    emojis_reais = [c for c in emojis if c != "`"]
    assert not emojis_reais, f"Emojis encontrados: {emojis_reais}"
