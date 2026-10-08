"""Observabilidade: avisar quando algo SAI DO NORMAL, não só quando bate o teto (regras, seção 10.2).

Linha de base robusta por sinal e por chave (usuário, IP, doador, ONG), separada por
faixa de 4 h e por dia útil/fim de semana (doação tem pico natural: sábado à noite
agitado não é anomalia):

    z = 0,6745 · (valor − mediana) / MAD          (z robusto de Iglewicz–Hoaglin)

Mediana e MAD não se deixam puxar pelas próprias anomalias, ao contrário de média e
desvio-padrão. Valores que já dispararam ALERTA não entram na linha de base: o
sistema não "aprende o ataque como normal".

Níveis: ATENÇÃO (z ≥ 3,5 ou 70% do teto) · ALERTA (z ≥ 7 ou 90% do teto) · CRÍTICO (teto).
Sinais de SEGURANÇA em ALERTA acionam o freio automático (src/observabilidade/freio.py);
sinais de NEGÓCIO só avisam.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum

import numpy as np

Z_ATENCAO = 3.5
Z_ALERTA = 7.0
FRACAO_TETO_ATENCAO = 0.70
FRACAO_TETO_ALERTA = 0.90
MIN_OBSERVACOES = 8
HISTORICO_MAXIMO = 60  # observações por (chave, faixa): ~2 meses de dias, ou 1 h de minutos


class Nivel(IntEnum):
    NORMAL = 0
    ATENCAO = 1
    ALERTA = 2
    CRITICO = 3


class TipoSinal(StrEnum):
    SEGURANCA = "seguranca"
    NEGOCIO = "negocio"
    IA = "ia"
    OPERACAO = "operacao"


@dataclass(frozen=True)
class Sinal:
    nome: str
    tipo: TipoSinal
    descricao: str
    janela: timedelta | None = None  # sinais de contagem; None = valor medido diretamente
    teto: float | None = None  # limite rígido que a regra no código já impõe
    piso_mad: float = 1.0  # evita z infinito quando o histórico é constante (ex.: sempre 0 falhas)
    por_faixa: bool = True  # separar por faixa horária e dia útil/fds
    # Grandezas multiplicativas (peso): "3x o normal" é variação natural, não anomalia. Na escala
    # linear a cauda longa gera alarme falso em ~6% dos lotes; em log, o desvio é medido em "vezes".
    escala_log: bool = False


SINAIS: dict[str, Sinal] = {s.nome: s for s in [
    Sinal("requisicoes_por_minuto", TipoSinal.SEGURANCA, "Requisições por usuário/IP", timedelta(minutes=1),
          teto=120, piso_mad=3, por_faixa=False),
    Sinal("falhas_login", TipoSinal.SEGURANCA, "Falhas de login por IP/conta", timedelta(minutes=15), teto=10),
    Sinal("bloqueios_guardrail", TipoSinal.SEGURANCA, "Textos bloqueados pelo guardrail", timedelta(hours=1), teto=20),
    Sinal("cadastros_por_dia", TipoSinal.NEGOCIO, "Lotes cadastrados pelo doador no dia", timedelta(days=1),
          piso_mad=1, por_faixa=False),
    Sinal("peso_lote", TipoSinal.NEGOCIO, "Peso do lote em relação ao histórico do doador", piso_mad=0.1,
          por_faixa=False, escala_log=True),
    Sinal("recusas_por_dia", TipoSinal.NEGOCIO, "Recusas de oferta da ONG no dia", timedelta(days=1), por_faixa=False),
    Sinal("gasto_caixa_dia", TipoSinal.NEGOCIO, "Gasto do caixa solidário da ONG no dia (R$)", teto=200,
          piso_mad=5, por_faixa=False),
    Sinal("latencia_p95_ms", TipoSinal.OPERACAO, "Latência p95 por rota (5 min)", piso_mad=20),
    Sinal("taxa_erro", TipoSinal.OPERACAO, "Fração de respostas 5xx por rota (5 min)", teto=0.2, piso_mad=0.01),
]}


@dataclass(frozen=True)
class Avaliacao:
    nivel: Nivel
    z: float | None
    mediana: float | None
    observacoes: int
    fracao_teto: float | None
    motivo: str


@dataclass(frozen=True)
class Alerta:
    ts: datetime
    sinal: str
    tipo: TipoSinal
    chave: str
    nivel: Nivel
    valor: float
    avaliacao: Avaliacao

    def para_dict(self) -> dict:
        a = self.avaliacao
        return {"ts": self.ts.isoformat(), "sinal": self.sinal, "tipo": str(self.tipo), "chave": self.chave,
                "nivel": self.nivel.name, "valor": round(self.valor, 4), "z": None if a.z is None else round(a.z, 2),
                "mediana": a.mediana, "observacoes": a.observacoes, "fracao_teto": a.fracao_teto, "motivo": a.motivo}


def _transformar(sinal: Sinal, valor: float) -> float:
    return float(np.log1p(max(valor, 0.0))) if sinal.escala_log else float(valor)


def faixa_horaria(ts: datetime) -> str:
    return f"{'fds' if ts.weekday() >= 5 else 'util'}-{ts.hour // 4 * 4:02d}h"


def z_robusto(valor: float, historico: np.ndarray, piso_mad: float) -> tuple[float, float]:
    mediana = float(np.median(historico))
    mad = float(np.median(np.abs(historico - mediana)))
    return 0.6745 * (valor - mediana) / max(mad, piso_mad, 0.05 * abs(mediana)), mediana


@dataclass
class LinhaDeBase:
    historico: dict[tuple[str, str, str], deque] = field(default_factory=lambda: defaultdict(
        lambda: deque(maxlen=HISTORICO_MAXIMO)))

    def _chave(self, sinal: Sinal, chave: str, ts: datetime) -> tuple[str, str, str]:
        return sinal.nome, chave, faixa_horaria(ts) if sinal.por_faixa else "*"

    def observar(self, sinal: Sinal, chave: str, ts: datetime, valor: float) -> None:
        self.historico[self._chave(sinal, chave, ts)].append(_transformar(sinal, valor))

    def avaliar(self, sinal: Sinal, chave: str, ts: datetime, valor: float) -> Avaliacao:
        hist = np.array(self.historico.get(self._chave(sinal, chave, ts), ()), dtype=float)
        nivel, motivos, z, mediana = Nivel.NORMAL, [], None, None
        if len(hist) >= MIN_OBSERVACOES:
            z, mediana = z_robusto(_transformar(sinal, valor), hist, sinal.piso_mad)
            if sinal.escala_log:
                mediana = round(float(np.expm1(mediana)), 3)  # devolve na unidade original
            if z >= Z_ALERTA:
                nivel, motivos = Nivel.ALERTA, [f"desvio forte (z={z:.1f})"]
            elif z >= Z_ATENCAO:
                nivel, motivos = Nivel.ATENCAO, [f"fora do normal (z={z:.1f})"]
        else:
            motivos.append("aquecendo: histórico insuficiente, só o teto vale")

        fracao = None
        if sinal.teto:
            fracao = round(valor / sinal.teto, 3)
            por_teto = (Nivel.CRITICO if fracao >= 1 else Nivel.ALERTA if fracao >= FRACAO_TETO_ALERTA
                        else Nivel.ATENCAO if fracao >= FRACAO_TETO_ATENCAO else Nivel.NORMAL)
            if por_teto > Nivel.NORMAL:
                motivos.append(f"{fracao:.0%} do teto")
            nivel = max(nivel, por_teto)
        return Avaliacao(nivel, z, mediana, len(hist), fracao, "; ".join(motivos))


class Monitor:
    """Recebe medições e contagens, compara com a linha de base e emite alertas.

    `ao_alertar` recebe cada Alerta (a API grava no log operacional e mostra no painel);
    `freio` é acionado para sinais de segurança em nível ALERTA ou acima.
    """

    def __init__(self, ao_alertar=None, freio=None):
        self.base = LinhaDeBase()
        self.alertas: list[Alerta] = []
        self._ao_alertar = ao_alertar
        self._freio = freio
        self._janelas: dict[tuple[str, str], tuple[datetime, float]] = {}
        self._ultimo_nivel: dict[tuple[str, str, datetime], Nivel] = {}

    def medir(self, nome_sinal: str, chave: str, ts: datetime, valor: float, aprender: bool = True) -> Alerta | None:
        sinal = SINAIS[nome_sinal]
        avaliacao = self.base.avaliar(sinal, chave, ts, valor)
        alerta = None
        if avaliacao.nivel > Nivel.NORMAL:
            alerta = Alerta(ts, sinal.nome, sinal.tipo, chave, avaliacao.nivel, float(valor), avaliacao)
            self._emitir(alerta)
        if aprender and avaliacao.nivel < Nivel.ALERTA:  # não aprender o ataque como normal
            self.base.observar(sinal, chave, ts, valor)
        return alerta

    def contar(self, nome_sinal: str, chave: str, ts: datetime, quantidade: float = 1) -> Alerta | None:
        """Contagem em janela fixa. A contagem parcial é comparada com o normal a cada evento
        (detecção durante a rajada); a contagem final da janela entra na linha de base."""
        sinal = SINAIS[nome_sinal]
        inicio = _inicio_janela(ts, sinal.janela)
        anterior = self._janelas.get((sinal.nome, chave))
        if anterior and anterior[0] != inicio:
            self._fechar_janela(sinal, chave, *anterior)
            anterior = None
        total = (anterior[1] if anterior else 0) + quantidade
        self._janelas[(sinal.nome, chave)] = (inicio, total)

        avaliacao = self.base.avaliar(sinal, chave, inicio, total)
        # Na mesma janela, só avisa quando o nível SOBE (evita uma enxurrada de alertas repetidos).
        chave_nivel = (sinal.nome, chave, inicio)
        if avaliacao.nivel > self._ultimo_nivel.get(chave_nivel, Nivel.NORMAL):
            self._ultimo_nivel[chave_nivel] = avaliacao.nivel
            alerta = Alerta(ts, sinal.nome, sinal.tipo, chave, avaliacao.nivel, total, avaliacao)
            self._emitir(alerta)
            return alerta
        return None

    def fechar_janelas(self, ate: datetime) -> None:
        """Fecha as janelas encerradas antes de `ate` (inclui na linha de base os períodos sem evento)."""
        for (nome, chave), (inicio, total) in list(self._janelas.items()):
            sinal = SINAIS[nome]
            if inicio + sinal.janela <= ate:
                self._fechar_janela(sinal, chave, inicio, total)
                del self._janelas[(nome, chave)]

    def _fechar_janela(self, sinal: Sinal, chave: str, inicio: datetime, total: float) -> None:
        if self._ultimo_nivel.pop((sinal.nome, chave, inicio), Nivel.NORMAL) < Nivel.ALERTA:
            self.base.observar(sinal, chave, inicio, total)

    def _emitir(self, alerta: Alerta) -> None:
        self.alertas.append(alerta)
        if self._ao_alertar:
            self._ao_alertar(alerta)
        if self._freio is not None and alerta.tipo == TipoSinal.SEGURANCA and alerta.nivel >= Nivel.ALERTA:
            self._freio.aplicar(alerta.chave, alerta.ts, motivo=f"{alerta.sinal}: {alerta.avaliacao.motivo}")


def _inicio_janela(ts: datetime, janela: timedelta) -> datetime:
    base = datetime(2000, 1, 3, tzinfo=ts.tzinfo)  # uma segunda-feira: janelas de dia começam à meia-noite
    return base + ((ts - base) // janela) * janela
