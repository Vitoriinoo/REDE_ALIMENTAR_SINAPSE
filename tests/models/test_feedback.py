"""Ciclo de feedback humano / RLHF adaptado (regras 10.4): defesa contra envenenamento e portão."""

from datetime import datetime, timedelta, timezone

import pytest

from src.models.feedback import (
    LIMITE_POR_ATOR_DIA,
    Feedback,
    RegistroDeVersoes,
    TipoFeedback,
    portao_de_promocao,
    validar_feedback,
)

T0 = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)


def _fb(ator, i, corrigiu=False, verificada=True, dia=0):
    return Feedback(ts=T0 + timedelta(days=dia, minutes=i), ator=ator, papel="doador", conta_verificada=verificada,
                    tipo=TipoFeedback.CATEGORIA, lote_id=f"L-{i:06d}", modelo_versao="nlp-v1",
                    sugerido="preparado", final="nao_perecivel" if corrigiu else "preparado")


def _honestos(n_atores=12, por_ator=12):
    """Doadores reais: corrigem a IA de vez em quando (~1 em 6)."""
    return [_fb(f"doador:{a}", a * 100 + i, corrigiu=(i + a) % 6 == 0, dia=i // 6)
            for a in range(n_atores) for i in range(por_ator)]


def test_conta_nao_verificada_nao_treina_modelo():
    r = validar_feedback([_fb("doador:novo", 1, verificada=False)])
    assert not r.aceitos and r.rejeitados[0][1] == "conta_nao_verificada"


def test_limite_diario_por_ator():
    r = validar_feedback([_fb("doador:a", i) for i in range(LIMITE_POR_ATOR_DIA + 5)])
    assert sum(m == "limite_diario" for _, m in r.rejeitados) == 5


def test_envenenador_que_corrige_tudo_vai_para_quarentena():
    """Ataque: um ator 'corrige' a IA em massa para ensinar que marmita é não perecível."""
    veneno = [_fb("doador:atacante", 5000 + i, corrigiu=True, dia=i // 15) for i in range(60)]
    r = validar_feedback(_honestos() + veneno)
    assert "doador:atacante" in r.quarentena
    assert not any(f.ator == "doador:atacante" for f in r.aceitos)
    assert not any(a.startswith("doador:") and a != "doador:atacante" for a in r.quarentena)  # sem falso positivo


def test_nenhum_ator_domina_os_rotulos_novos():
    muitos = [_fb("doador:grande", i, dia=i // 18) for i in range(90)]
    r = validar_feedback(_honestos() + muitos)
    assert sum(f.ator == "doador:grande" for f in r.aceitos) <= max(5, round(0.02 * 234) + 1)


def test_portao_barra_modelo_pior_e_exige_outro_humano():
    atual = {"f1_macro": 0.90, "recall_critica": 0.95}
    melhor = {"f1_macro": 0.91, "recall_critica": 0.96}
    kw = dict(metrica_principal="f1_macro", metas_minimas={"recall_critica": 0.90}, treinado_por="eng:1")
    assert portao_de_promocao(atual, melhor, aprovado_por="eng:2", **kw).promover
    assert not portao_de_promocao(atual, melhor, aprovado_por="eng:1", **kw).promover  # segregação
    assert not portao_de_promocao(atual, melhor, aprovado_por=None, **kw).promover
    pior = {"f1_macro": 0.85, "recall_critica": 0.96}
    assert not portao_de_promocao(atual, pior, aprovado_por="eng:2", **kw).promover
    abaixo_da_meta = {"f1_macro": 0.92, "recall_critica": 0.85}
    assert not portao_de_promocao(atual, abaixo_da_meta, aprovado_por="eng:2", **kw).promover


def test_promocao_e_rollback(tmp_path):
    reg = RegistroDeVersoes(tmp_path / "versoes.json")
    ok = portao_de_promocao({"f1": 0.8}, {"f1": 0.8}, metrica_principal="f1", metas_minimas={},
                            treinado_por="a", aprovado_por="b")
    reg.promover("v1", "sha1", {"f1": 0.8}, ok, "b")
    reg.promover("v2", "sha2", {"f1": 0.81}, ok, "b")
    assert reg.ativa["versao"] == "v2"
    assert reg.rollback("drift em produção")["versao"] == "v1"
    assert RegistroDeVersoes(tmp_path / "versoes.json").ativa["versao"] == "v1"  # persistido


def test_promocao_barrada_nao_entra_no_registro(tmp_path):
    reg = RegistroDeVersoes(tmp_path / "versoes.json")
    barrada = portao_de_promocao({"f1": 0.9}, {"f1": 0.5}, metrica_principal="f1", metas_minimas={},
                                 treinado_por="a", aprovado_por="b")
    with pytest.raises(PermissionError):
        reg.promover("v9", "sha", {"f1": 0.5}, barrada, "b")
    assert reg.ativa is None
