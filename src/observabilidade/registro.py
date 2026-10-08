"""Registro de eventos: completo em COBERTURA, mínimo em CONTEÚDO (regras, seção 10.1).

Duas trilhas:
- OPERACIONAL (90 dias): acesso, validação rejeitada, alertas. Um arquivo por dia.
- AUDITORIA (5 anos): decisões, IA, dinheiro, administração. Um arquivo por mês e uma
  CADEIA de HMAC: cada registro guarda o hash do anterior. Alterar, apagar ou reordenar
  uma linha quebra a cadeia, e `verificar_cadeia` aponta onde. Com HMAC (e não SHA-256
  puro), quem consegue escrever no arquivo mas não tem a chave não recalcula a cadeia.

Toda gravação passa por `minimizar` (chaves proibidas removidas, CPF/CNPJ/e-mail/telefone
mascarados): a proteção não depende de quem chama lembrar.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

from src.seguranca.minimizacao import mascarar_texto, minimizar
from src.seguranca.segredos import obter_segredo

VERSAO_REGRAS = "2.0"
GENESE = "0" * 64


class Trilha(StrEnum):
    OPERACIONAL = "operacional"
    AUDITORIA = "auditoria"


class Resultado(StrEnum):
    SUCESSO = "sucesso"
    NEGADO = "negado"
    ERRO = "erro"


RETENCAO = {Trilha.OPERACIONAL: timedelta(days=90), Trilha.AUDITORIA: timedelta(days=5 * 365 + 1)}

# Liga a requisição a todas as decisões que ela gerou (a API define no início de cada requisição).
correlacao_atual: ContextVar[str | None] = ContextVar("correlacao_atual", default=None)


def _canonico(registro: dict) -> bytes:
    return json.dumps(registro, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class RegistroAuditavel:
    def __init__(self, diretorio: Path, chave: bytes | None = None, relogio: Callable[[], datetime] = _agora_utc):
        self.dir = Path(diretorio)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._chave = chave or obter_segredo("REDE_ALIMENTA_CHAVE_LOG", "dev-log-somente-dados-sinteticos")
        self._relogio = relogio
        self._trava = threading.Lock()
        self._ultimo_hash = self._recuperar_ultimo_hash()

    # ---------- gravação ----------
    def registrar(
        self,
        trilha: Trilha,
        *,
        componente: str,
        acao: str,
        ator: str,
        papel: str,
        recurso: str | None = None,
        resultado: Resultado = Resultado.SUCESSO,
        detalhes: dict | None = None,
        correlacao_id: str | None = None,
    ) -> dict:
        agora = self._relogio()
        registro = {
            "evento_id": str(uuid.uuid4()),
            "ts": agora.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "trilha": str(trilha),
            "correlacao_id": correlacao_id or correlacao_atual.get(),
            "componente": componente,
            "acao": acao,
            "ator": mascarar_texto(ator),
            "papel": papel,
            "recurso": recurso,
            "resultado": str(resultado),
            "detalhes": minimizar(detalhes or {}),
            "versao_regras": VERSAO_REGRAS,
        }
        with self._trava:
            if trilha == Trilha.AUDITORIA:
                registro["hash_anterior"] = self._ultimo_hash
                registro["hash"] = self._hmac(registro)
                self._ultimo_hash = registro["hash"]
            with open(self._arquivo(trilha, agora), "a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")
        return registro

    def _hmac(self, registro: dict) -> str:
        sem_hash = {k: v for k, v in registro.items() if k != "hash"}
        return hmac.new(self._chave, _canonico(sem_hash), hashlib.sha256).hexdigest()

    def _arquivo(self, trilha: Trilha, quando: datetime) -> Path:
        if trilha == Trilha.AUDITORIA:
            return self.dir / f"auditoria-{quando:%Y-%m}.jsonl"
        return self.dir / f"operacional-{quando:%Y-%m-%d}.jsonl"

    def _arquivos(self, trilha: Trilha) -> list[Path]:
        return sorted(self.dir.glob(f"{trilha}-*.jsonl"))

    def _ancora(self) -> str:
        """Último hash apagado pela retenção (protegido por HMAC: forjar a âncora também é detectado)."""
        caminho = self.dir / "auditoria-ancora.json"
        if not caminho.exists():
            return GENESE
        ancora = json.loads(caminho.read_text(encoding="utf-8"))
        esperado = hmac.new(self._chave, f"{ancora['hash']}|{ancora['removido']}".encode(), hashlib.sha256).hexdigest()
        return ancora["hash"] if hmac.compare_digest(ancora.get("hmac", ""), esperado) else "ANCORA_INVALIDA"

    def _recuperar_ultimo_hash(self) -> str:
        for arquivo in reversed(self._arquivos(Trilha.AUDITORIA)):
            linhas = arquivo.read_text(encoding="utf-8").splitlines()
            if linhas:
                return json.loads(linhas[-1])["hash"]
        return self._ancora()

    # ---------- leitura e verificação ----------
    def ler(self, trilha: Trilha) -> list[dict]:
        return [json.loads(linha) for arq in self._arquivos(trilha)
                for linha in arq.read_text(encoding="utf-8").splitlines() if linha.strip()]

    def verificar_cadeia(self) -> list[str]:
        """Problemas da trilha de auditoria (lista vazia = íntegra)."""
        problemas, esperado = [], self._ancora()
        for arq in self._arquivos(Trilha.AUDITORIA):
            for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), start=1):
                try:
                    registro = json.loads(linha)
                except json.JSONDecodeError:
                    problemas.append(f"{arq.name}:{n}: linha corrompida")
                    continue
                if registro.get("hash_anterior") != esperado:
                    problemas.append(f"{arq.name}:{n}: elo quebrado (linha apagada, inserida ou reordenada)")
                if not hmac.compare_digest(registro.get("hash", ""), self._hmac(registro)):
                    problemas.append(f"{arq.name}:{n}: conteúdo alterado (HMAC não confere)")
                esperado = registro.get("hash", "")
        return problemas

    # ---------- retenção ----------
    def aplicar_retencao(self, agora: datetime | None = None) -> list[str]:
        """Apaga arquivos inteiros além do prazo. Na auditoria, guarda a âncora do último hash apagado."""
        agora = agora or self._relogio()
        removidos = []
        for trilha in Trilha:
            limite = agora - RETENCAO[trilha]
            for arq in self._arquivos(trilha):
                sufixo = arq.stem.split("-", 1)[1]
                if trilha == Trilha.AUDITORIA:
                    ano, mes = map(int, sufixo.split("-"))
                    fim = datetime(ano + (mes == 12), mes % 12 + 1, 1, tzinfo=timezone.utc)
                else:
                    fim = datetime.strptime(sufixo, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
                if fim <= limite:
                    if trilha == Trilha.AUDITORIA:
                        linhas = arq.read_text(encoding="utf-8").splitlines()
                        if linhas:
                            ultimo = json.loads(linhas[-1])["hash"]
                            selo = hmac.new(self._chave, f"{ultimo}|{arq.name}".encode(), hashlib.sha256).hexdigest()
                            (self.dir / "auditoria-ancora.json").write_text(
                                json.dumps({"hash": ultimo, "removido": arq.name, "hmac": selo}), encoding="utf-8")
                    arq.unlink()
                    removidos.append(arq.name)
        return removidos
