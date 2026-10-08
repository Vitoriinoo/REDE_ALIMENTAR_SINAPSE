"""Demonstração do ciclo de feedback humano (RLHF adaptado, regras 10.4) com o NLP real.

1. A IA SUGERE: o classificador de similaridade sugere a categoria de textos do período
   de VALIDAÇÃO.
2. O HUMANO CORRIGE: doadores honestos confirmam ou corrigem (a categoria verdadeira).
   Um ATACANTE "corrige" marmitas para não perecível em massa (envenenamento), e uma conta
   não verificada também tenta contribuir.
3. VALIDAÇÃO: `validar_feedback` filtra (conta verificada, limite diário, quarentena, cota).
4. RETREINO COM PORTÃO: as correções aceitas viram exemplos novos do classificador. O
   candidato é avaliado no conjunto de TESTE FIXO (nunca recebe feedback) e passa pelo portão.

Para comparar, o mesmo retreino é feito SEM a validação (com o veneno).

Ressalva honesta: os textos do teste vêm do mesmo gerador de frases do dataset simulado,
então o ganho do candidato limpo tende a ser otimista. O conjunto independente escrito
pelo grupo (tests/dados/) é a verificação real.

Uso:
    python -m src.models.demo_feedback
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.metrics import accuracy_score

from src.models import features as F
from src.models.avaliar_nlp import amostra_teste
from src.models.exemplos_nlp import EXEMPLOS_CATEGORIA
from src.models.feedback import Feedback, TipoFeedback, portao_de_promocao, validar_feedback
from src.models.nlp import ClassificadorSimilaridade
from src.regras.dominio import Categoria
from src.seguranca.minimizacao import pseudonimo

SEED = 42
SAIDA = F.RAIZ / "reports" / "feedback_demo.json"


def _avaliar(clf: ClassificadorSimilaridade, df) -> dict:
    pred = [str(s.categoria) for s in clf.sugerir_lote(df["descricao_texto"].tolist())]
    ok = np.array(pred) == df["categoria"].to_numpy()
    por_cat = {c: round(float(ok[df["categoria"].to_numpy() == c].mean()), 3) for c in sorted(df["categoria"].unique())}
    return {"acuracia": round(accuracy_score(df["categoria"], pred), 4), "acuracia_preparado": por_cat["preparado"],
            "por_categoria": por_cat}


def _com_exemplos(clf: ClassificadorSimilaridade, extras: dict[str, list[str]]) -> ClassificadorSimilaridade:
    """Mesmo modelo de embeddings, centroides recalculados com os exemplos novos (o 'retreino')."""
    exemplos = {c: list(v) + extras.get(str(c), []) for c, v in EXEMPLOS_CATEGORIA.items()}
    novo = object.__new__(ClassificadorSimilaridade)
    novo.__dict__.update(clf.__dict__)
    novo._categorias, novo._centroides_cat = clf._centroides(exemplos)
    return novo


def main() -> None:
    rng = np.random.default_rng(SEED)
    _, validacao, _ = F.split_temporal(F.carregar_lotes_validos())
    # Período de validação inteiro (~19 feedbacks por doador): a quarentena compara o ator com os
    # pares e só funciona quando eles têm histórico (>= 10 feedbacks). Com pouco feedback, só a
    # cota por ator segura o atacante.
    validacao = validacao[~validacao["texto_adversarial"]].reset_index(drop=True)
    teste_fixo = amostra_teste()

    base = ClassificadorSimilaridade()
    metricas_base = _avaliar(base, teste_fixo)

    # Passos 1 e 2: a IA sugere e os doadores (honestos) confirmam ou corrigem.
    sugeridas = [str(s.categoria) for s in base.sugerir_lote(validacao["descricao_texto"].tolist())]
    t0 = datetime(2026, 3, 1, 9, tzinfo=timezone.utc)
    feedbacks, texto_por_lote = [], {}
    for i, (lote, sug) in enumerate(zip(validacao.itertuples(), sugeridas)):
        texto_por_lote[lote.lote_id] = lote.descricao_texto
        feedbacks.append(Feedback(ts=t0 + timedelta(hours=2 * i), ator=pseudonimo("doador", lote.doador_id),
                                  papel="doador", conta_verificada=True, tipo=TipoFeedback.CATEGORIA,
                                  lote_id=lote.lote_id, modelo_versao="nlp-similaridade-v1", sugerido=sug,
                                  final=lote.categoria))
    # Ataque: 80 "correções" de marmitas para não perecível, 20 por dia; e uma conta não verificada.
    marmitas = validacao[validacao["categoria"] == "preparado"].sample(80, random_state=SEED, replace=True)
    for j, lote in enumerate(marmitas.itertuples()):
        lid = f"X-{j:05d}"
        texto_por_lote[lid] = lote.descricao_texto
        feedbacks.append(Feedback(ts=t0 + timedelta(days=j // 20, minutes=j), ator="doador:atacante", papel="doador",
                                  conta_verificada=True, tipo=TipoFeedback.CATEGORIA, lote_id=lid,
                                  modelo_versao="nlp-similaridade-v1", sugerido="preparado", final="nao_perecivel"))
    for j in range(30):
        feedbacks.append(Feedback(ts=t0 + timedelta(minutes=j), ator="doador:sem-verificacao", papel="doador",
                                  conta_verificada=False, tipo=TipoFeedback.CATEGORIA, lote_id=f"Y-{j:05d}",
                                  modelo_versao="nlp-similaridade-v1", sugerido="padaria", final="congelado"))

    # Passo 3: validação.
    resultado = validar_feedback(feedbacks)

    def extras(lista, so_correcoes: bool = False) -> dict[str, list[str]]:
        """Rótulo humano (final) de cada feedback vira exemplo novo da classe."""
        saida: dict[str, list[str]] = {}
        for fb in lista:
            if (fb.corrigiu or not so_correcoes) and fb.lote_id in texto_por_lote:
                saida.setdefault(fb.final, []).append(texto_por_lote[fb.lote_id])
        return saida

    # Passo 4: retreino + portão (no teste fixo).
    metas = {"acuracia_preparado": metricas_base["acuracia_preparado"] - 0.02}
    kw = dict(metrica_principal="acuracia", metas_minimas=metas, treinado_por="eng:ia", aprovado_por="eng:produto")
    verificados = [f for f in feedbacks if f.conta_verificada]
    candidatos = {
        # Certo: todos os rótulos humanos validados (confirmações + correções).
        "validado_todos_os_rotulos": extras(resultado.aceitos),
        # Ingênuo: só as correções. São os textos difíceis: puxam os centroides para a zona de confusão.
        "validado_so_correcoes": extras(resultado.aceitos, so_correcoes=True),
        # Sem o passo 3: o veneno do atacante entra no treino.
        "sem_validacao_envenenado": extras(verificados),
    }
    resultados = {}
    for nome, ex in candidatos.items():
        m = _avaliar(_com_exemplos(base, ex), teste_fixo)
        d = portao_de_promocao(metricas_base, m, **kw)
        resultados[nome] = m | {"exemplos_novos": sum(map(len, ex.values())),
                                "portao": {"promover": d.promover, "motivos": d.motivos}}

    relatorio = {
        "feedbacks_recebidos": len(feedbacks),
        "validacao": resultado.resumo() | {"quarentena": resultado.quarentena},
        "atacante_aceito": sum(f.ator == "doador:atacante" for f in resultado.aceitos),
        "nao_verificado_aceito": sum(f.ator == "doador:sem-verificacao" for f in resultado.aceitos),
        "modelo_atual": metricas_base,
        "candidatos": resultados,
        "ressalva": "Textos do teste vêm do mesmo gerador do dataset simulado: o ganho do candidato limpo é otimista.",
    }
    SAIDA.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
