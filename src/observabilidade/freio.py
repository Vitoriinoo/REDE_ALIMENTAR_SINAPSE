"""Limite de requisições + freio automático e reversível (regras 10.2; aula 6, controle C7).

- Limite normal: 120 requisições/min por chave (usuário ou IP). Acima disso a requisição
  é recusada (HTTP 429): é o TETO, regra fixa no código.
- Freio: quando a observabilidade vê um desvio forte num sinal de segurança, o limite da
  chave cai para 10/min por 15 minutos. Expira sozinho ou o admin libera; tudo é logado
  e um humano revisa cada freio aplicado.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

LIMITE_NORMAL_POR_MIN = 120
LIMITE_FREADO_POR_MIN = 10
DURACAO_FREIO = timedelta(minutes=15)


@dataclass(frozen=True)
class FreioAtivo:
    chave: str
    inicio: datetime
    fim: datetime
    motivo: str


class Freio:
    def __init__(self, ao_mudar=None):
        self._ativos: dict[str, FreioAtivo] = {}
        self._requisicoes: dict[str, deque] = defaultdict(deque)
        self._ao_mudar = ao_mudar  # callback(acao, freio) para o log de auditoria

    def aplicar(self, chave: str, ts: datetime, motivo: str, duracao: timedelta = DURACAO_FREIO) -> FreioAtivo:
        freio = FreioAtivo(chave, ts, ts + duracao, motivo)
        self._ativos[chave] = freio
        if self._ao_mudar:
            self._ao_mudar("FREIO_APLICADO", freio)
        return freio

    def liberar(self, chave: str, ts: datetime) -> bool:
        freio = self._ativos.pop(chave, None)
        if freio and self._ao_mudar:
            self._ao_mudar("FREIO_LIBERADO", freio)
        return freio is not None

    def ativo(self, chave: str, ts: datetime) -> FreioAtivo | None:
        freio = self._ativos.get(chave)
        if freio and ts >= freio.fim:
            del self._ativos[chave]
            if self._ao_mudar:
                self._ao_mudar("FREIO_EXPIRADO", freio)
            return None
        return freio

    def limite(self, chave: str, ts: datetime) -> int:
        return LIMITE_FREADO_POR_MIN if self.ativo(chave, ts) else LIMITE_NORMAL_POR_MIN

    def permitir(self, chave: str, ts: datetime) -> bool:
        """Janela deslizante de 1 minuto. Requisição recusada não conta (não prolonga o bloqueio)."""
        fila = self._requisicoes[chave]
        while fila and ts - fila[0] >= timedelta(minutes=1):
            fila.popleft()
        if len(fila) >= self.limite(chave, ts):
            return False
        fila.append(ts)
        return True
