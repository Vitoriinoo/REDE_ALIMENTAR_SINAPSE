"""Sugestão de categoria e armazenamento a partir do texto livre do doador (regras 4.4).

Fluxo: texto -> guardrail de entrada -> classificador (Hugging Face) -> SUGESTÃO -> doador confirma.

Dois classificadores, ambos escolhem só rótulos de uma lista FIXA (sem agência: mesmo que
uma instrução maliciosa passe pelo guardrail, o pior caso é uma sugestão errada, que o
doador confirma e as regras de negócio revalidam):

- `ClassificadorSimilaridade` (PADRÃO): embeddings multilíngues + poucos exemplos por
  classe (src/models/exemplos_nlp.py); o texto vai para a classe mais parecida.
- `ClassificadorZeroShotNLI` (BASELINE): zero-shot por inferência textual (NLI). Ficou em
  ~49% de acurácia e ~3,3 s/texto; mantido para documentar por que foi substituído.

Cadeia de suprimentos: modelos fixados por commit, carregados só em safetensors, sem
`trust_remote_code`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.models.exemplos_nlp import EXEMPLOS_ARMAZENAMENTO, EXEMPLOS_CATEGORIA
from src.regras.dominio import CADEIA_FRIA, Armazenamento, Categoria
from src.seguranca.guardrails import filtrar_entrada

MODELO_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # licença Apache-2.0
REVISAO_EMBEDDINGS = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"

MODELO_NLI = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"  # licença MIT
REVISAO_NLI = "8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c"


@dataclass
class Sugestao:
    bloqueado: bool
    motivos_bloqueio: list[str]
    categoria: Categoria | None = None
    confianca_categoria: float | None = None
    armazenamento: Armazenamento | None = None
    confianca_armazenamento: float | None = None
    requer_confirmacao: bool = True  # sempre: a sugestão nunca é gravada sem o doador confirmar


class _ClassificadorBase:
    """Guardrail + montagem da sugestão; as subclasses só implementam `_prever`."""

    def _prever(self, textos: list[str]) -> list[tuple[Categoria, float, Armazenamento, float]]:
        raise NotImplementedError

    def sugerir_lote(self, textos: list[str]) -> list[Sugestao]:
        filtrados = [filtrar_entrada(t) for t in textos]
        sugestoes = [Sugestao(bloqueado=f.bloqueado, motivos_bloqueio=f.motivos) for f in filtrados]
        livres = [i for i, f in enumerate(filtrados) if not f.bloqueado]
        if not livres:
            return sugestoes
        previsoes = self._prever([filtrados[i].texto for i in livres])
        for i, (categoria, conf_c, armazenamento, conf_a) in zip(livres, previsoes):
            s = sugestoes[i]
            s.categoria, s.confianca_categoria = categoria, round(float(conf_c), 4)
            if categoria in CADEIA_FRIA:
                s.armazenamento, s.confianca_armazenamento = armazenamento, round(float(conf_a), 4)
            else:  # armazenamento só importa para a cadeia fria
                s.armazenamento, s.confianca_armazenamento = Armazenamento.AMBIENTE, None
        return sugestoes

    def sugerir(self, texto: str) -> Sugestao:
        return self.sugerir_lote([texto])[0]


class ClassificadorSimilaridade(_ClassificadorBase):
    """Classe = maior similaridade de cosseno com o centroide dos exemplos da classe.

    A "confiança" é um softmax das similaridades (temperatura baixa), só para ordenar
    e sinalizar sugestões duvidosas ao doador; não é uma probabilidade calibrada.
    """

    TEMPERATURA = 0.05

    def __init__(self, modelo: str = MODELO_EMBEDDINGS, revisao: str = REVISAO_EMBEDDINGS):
        from sentence_transformers import SentenceTransformer  # import tardio: só quem usa paga o custo do torch

        self._modelo = SentenceTransformer(
            modelo, revision=revisao, device="cpu", trust_remote_code=False, model_kwargs={"use_safetensors": True}
        )
        self._categorias, self._centroides_cat = self._centroides(EXEMPLOS_CATEGORIA)
        self._armazenamentos, self._centroides_arm = self._centroides(EXEMPLOS_ARMAZENAMENTO)

    def _embed(self, textos: list[str]) -> np.ndarray:
        return self._modelo.encode(textos, normalize_embeddings=True, batch_size=64, show_progress_bar=False)

    def _centroides(self, exemplos: dict) -> tuple[list, np.ndarray]:
        classes = list(exemplos)
        centroides = np.stack([self._embed(exemplos[c]).mean(axis=0) for c in classes])
        return classes, centroides / np.linalg.norm(centroides, axis=1, keepdims=True)

    def _escolher(self, emb: np.ndarray, classes: list, centroides: np.ndarray):
        sim = emb @ centroides.T
        pesos = np.exp((sim - sim.max(axis=1, keepdims=True)) / self.TEMPERATURA)
        prob = pesos / pesos.sum(axis=1, keepdims=True)
        idx = prob.argmax(axis=1)
        return [classes[i] for i in idx], prob[np.arange(len(idx)), idx]

    def _prever(self, textos):
        emb = self._embed(textos)
        cats, conf_c = self._escolher(emb, self._categorias, self._centroides_cat)
        arms, conf_a = self._escolher(emb, self._armazenamentos, self._centroides_arm)
        return list(zip(cats, conf_c, arms, conf_a))


class ClassificadorZeroShotNLI(_ClassificadorBase):
    """Baseline documentado (substituído): zero-shot por NLI."""

    ROTULOS_CATEGORIA = {
        "comida pronta, marmitas ou refeições": Categoria.PREPARADO,
        "laticínios, iogurtes, queijos ou frios": Categoria.REFRIGERADO,
        "carnes ou frango congelados": Categoria.CONGELADO,
        "frutas, verduras ou legumes": Categoria.HORTIFRUTI,
        "pães ou bolos": Categoria.PADARIA,
        "grãos, enlatados ou alimentos secos embalados": Categoria.NAO_PERECIVEL,
    }
    ROTULOS_ARMAZENAMENTO = {
        "guardado na geladeira": Armazenamento.REFRIGERADO,
        "congelado no freezer": Armazenamento.CONGELADO,
        "em temperatura ambiente, fora da geladeira": Armazenamento.AMBIENTE,
    }

    def __init__(self, modelo: str = MODELO_NLI, revisao: str = REVISAO_NLI, batch_size: int = 16):
        from transformers import pipeline

        self._pipe = pipeline("zero-shot-classification", model=modelo, revision=revisao, device=-1,
                              model_kwargs={"use_safetensors": True}, trust_remote_code=False)
        self._batch = batch_size

    def _classificar(self, textos, rotulos: dict, template: str):
        saidas = self._pipe(textos, candidate_labels=list(rotulos), hypothesis_template=template, batch_size=self._batch)
        saidas = [saidas] if isinstance(saidas, dict) else saidas
        return [(rotulos[s["labels"][0]], s["scores"][0]) for s in saidas]

    def _prever(self, textos):
        cats = self._classificar(textos, self.ROTULOS_CATEGORIA, "Este alimento é {}.")
        arms = self._classificar(textos, self.ROTULOS_ARMAZENAMENTO, "Este alimento está {}.")
        return [(c, cc, a, ca) for (c, cc), (a, ca) in zip(cats, arms)]


ClassificadorLote = ClassificadorSimilaridade  # classificador padrão da plataforma
