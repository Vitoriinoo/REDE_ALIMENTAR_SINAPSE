"""Declaração de Doação: documento auditável, assinado e imutável (regras, seção 4.5).

Registra O QUE foi disponibilizado, POR QUEM (pseudônimo), QUANDO e EM QUE CONDIÇÕES.

Integridade (aula 3, biblioteca `cryptography`):
1. o conteúdo vira JSON CANÔNICO (chaves ordenadas, UTF-8, sem espaços): o mesmo
   conteúdo produz sempre os mesmos bytes;
2. SHA-256 dos bytes = identidade do documento;
3. assinatura RSA-PSS (SHA-256, MGF1, salt máximo) com a chave privada da plataforma.
Qualquer pessoa com a chave PÚBLICA verifica que o documento não foi alterado.

Imutabilidade: o repositório só INCLUI (arquivo aberto em modo "x"). Uma correção é
uma nova versão que aponta para o hash da anterior; nada é sobrescrito nem apagado.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from src.regras.questionario import PERGUNTAS, TEXTO_DECLARACAO, perguntas_aplicaveis
from src.seguranca.minimizacao import mascarar_texto

VERSAO_SCHEMA = "1.0"
VERSAO_REGRAS = "2.0"
ALGORITMO = "RSA-PSS-SHA256"
TAMANHO_CHAVE = 3072

_PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)


class DeclaracaoInvalida(RuntimeError):
    pass


# --- JSON canônico ---------------------------------------------------------------------------
def _para_json(valor: Any) -> Any:
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            raise ValueError("data sem fuso horário não entra em documento auditável")
        return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(valor, dict):
        return {str(k): _para_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset)):
        itens = [_para_json(v) for v in valor]
        return sorted(itens) if isinstance(valor, (set, frozenset)) else itens
    if isinstance(valor, float) and valor != valor:  # NaN não tem forma canônica
        raise ValueError("NaN não entra em documento auditável")
    if hasattr(valor, "value"):  # Enum
        return valor.value
    return valor


def json_canonico(conteudo: dict) -> bytes:
    return json.dumps(_para_json(conteudo), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


# --- Chaves ------------------------------------------------------------------------------------
def gerar_chave_privada() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=TAMANHO_CHAVE)


def chave_id(publica: rsa.RSAPublicKey) -> str:
    """Impressão digital curta da chave pública (permite trocar a chave sem perder a verificação)."""
    der = publica.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()[:16]


def carregar_chave_privada(caminho: Path | None = None, senha: bytes | None = None) -> rsa.RSAPrivateKey:
    """Lê do caminho indicado ou de REDE_ALIMENTA_CHAVE_DECLARACAO (caminho do PEM)."""
    caminho = caminho or Path(os.environ["REDE_ALIMENTA_CHAVE_DECLARACAO"])
    senha = senha if senha is not None else os.environ.get("REDE_ALIMENTA_SENHA_CHAVE_DECLARACAO", "").encode() or None
    return serialization.load_pem_private_key(caminho.read_bytes(), password=senha)


def salvar_par_de_chaves(chave: rsa.RSAPrivateKey, privada: Path, publica: Path, senha: bytes | None = None) -> None:
    cifra = serialization.BestAvailableEncryption(senha) if senha else serialization.NoEncryption()
    privada.parent.mkdir(parents=True, exist_ok=True)
    with open(privada, "xb") as f:  # nunca sobrescreve uma chave existente
        f.write(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, cifra))
    publica.parent.mkdir(parents=True, exist_ok=True)
    publica.write_bytes(chave.public_key().public_bytes(serialization.Encoding.PEM,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo))


# --- Documento ---------------------------------------------------------------------------------
@dataclass(frozen=True)
class DeclaracaoAssinada:
    conteudo: dict
    sha256: str
    assinatura: str  # base64
    algoritmo: str
    chave_id: str

    def para_dict(self) -> dict:
        return {"conteudo": self.conteudo, "sha256": self.sha256, "assinatura": self.assinatura,
                "algoritmo": self.algoritmo, "chave_id": self.chave_id}

    @classmethod
    def de_dict(cls, d: dict) -> DeclaracaoAssinada:
        return cls(d["conteudo"], d["sha256"], d["assinatura"], d["algoritmo"], d["chave_id"])


def montar_conteudo(
    *,
    lote_id: str,
    doador_pseudonimo: str,
    tipo_doador,
    categoria,
    armazenamento,
    peso_kg: float,
    descricao: str,
    validade_efetiva: datetime | None,
    base_validade: dict,
    rota_expressa: bool,
    respostas,
    motivos_bloqueio: list[str],
    sugestao_ia: dict | None,
    emitida_em: datetime,
    declaracao_id: str | None = None,
    versao: int = 1,
    hash_versao_anterior: str | None = None,
) -> dict:
    respostas_dict = {k: _para_json(v) for k, v in vars(respostas).items()}
    campos = {"Q1": "origem", "Q2": "embalagem_integra", "Q3": "alergenicos", "Q4": "requer_preparo",
              "Q5": "declaracao_condicoes", "Q6": "exposto_consumidor", "Q7": "rotulo_visivel",
              "Q8": "descongelado", "Q9": "lacrado_original", "Q10": "selecionado"}
    questionario = {
        pid: {"pergunta": PERGUNTAS[pid], "resposta": respostas_dict[campos[pid]]}
        for pid in perguntas_aplicaveis(categoria, tipo_doador)
    }
    return {
        "tipo": "DECLARACAO_DE_DOACAO",
        "schema": VERSAO_SCHEMA,
        "versao_regras": VERSAO_REGRAS,
        "declaracao_id": declaracao_id or str(uuid.uuid4()),
        "versao": versao,
        "hash_versao_anterior": hash_versao_anterior,
        "emitida_em": emitida_em,
        "lote_id": lote_id,
        "doador": {"pseudonimo": doador_pseudonimo, "tipo": tipo_doador},
        "alimento": {
            # Texto livre pode conter dado pessoal digitado pelo doador: vai mascarado.
            "descricao": mascarar_texto(descricao)[:500],
            "categoria_confirmada": categoria,
            "armazenamento_confirmado": armazenamento,
            "peso_kg": round(float(peso_kg), 2),
            "validade_efetiva": validade_efetiva,
            "base_do_calculo_da_validade": base_validade,
            "rota_expressa": rota_expressa,
        },
        "sugestao_ia": sugestao_ia,
        "questionario": questionario,
        "texto_declaracao": TEXTO_DECLARACAO,
        "resultado": "BLOQUEADA" if motivos_bloqueio else "ACEITA",
        "motivos_bloqueio": list(motivos_bloqueio),
    }


def assinar(conteudo: dict, chave: rsa.RSAPrivateKey) -> DeclaracaoAssinada:
    canonico = json_canonico(conteudo)
    assinatura = chave.sign(canonico, _PSS, hashes.SHA256())
    return DeclaracaoAssinada(
        conteudo=json.loads(canonico), sha256=hashlib.sha256(canonico).hexdigest(),
        assinatura=base64.b64encode(assinatura).decode(), algoritmo=ALGORITMO, chave_id=chave_id(chave.public_key()),
    )


def verificar(declaracao: DeclaracaoAssinada, publica: rsa.RSAPublicKey) -> bool:
    """True só se o conteúdo bate com o hash E a assinatura é da chave informada."""
    if declaracao.algoritmo != ALGORITMO or declaracao.chave_id != chave_id(publica):
        return False
    canonico = json_canonico(declaracao.conteudo)
    if hashlib.sha256(canonico).hexdigest() != declaracao.sha256:
        return False
    try:
        publica.verify(base64.b64decode(declaracao.assinatura), canonico, _PSS, hashes.SHA256())
    except (InvalidSignature, ValueError):
        return False
    return True


# --- Repositório só de inclusão ----------------------------------------------------------------
class RepositorioDeclaracoes:
    def __init__(self, diretorio: Path):
        self.dir = diretorio
        self.dir.mkdir(parents=True, exist_ok=True)

    def _caminho(self, declaracao_id: str, versao: int) -> Path:
        uuid.UUID(declaracao_id)  # o id vira nome de arquivo: só aceita UUID (sem path traversal)
        return self.dir / f"{declaracao_id}-v{versao:03d}.json"

    def salvar(self, declaracao: DeclaracaoAssinada) -> Path:
        c = declaracao.conteudo
        if c["versao"] > 1:
            anterior = self.ler(c["declaracao_id"], c["versao"] - 1)
            if c["hash_versao_anterior"] != anterior.sha256:
                raise DeclaracaoInvalida("A nova versão não aponta para o hash da versão anterior.")
        caminho = self._caminho(c["declaracao_id"], c["versao"])
        with open(caminho, "x", encoding="utf-8") as f:  # "x": falha se já existir (imutável)
            json.dump(declaracao.para_dict(), f, ensure_ascii=False, indent=1)
        return caminho

    def ler(self, declaracao_id: str, versao: int) -> DeclaracaoAssinada:
        return DeclaracaoAssinada.de_dict(json.loads(self._caminho(declaracao_id, versao).read_text(encoding="utf-8")))

    def versoes(self, declaracao_id: str) -> list[DeclaracaoAssinada]:
        uuid.UUID(declaracao_id)
        return [DeclaracaoAssinada.de_dict(json.loads(p.read_text(encoding="utf-8")))
                for p in sorted(self.dir.glob(f"{declaracao_id}-v*.json"))]

    def verificar_historico(self, declaracao_id: str, publica: rsa.RSAPublicKey) -> list[str]:
        """Problemas encontrados no histórico (lista vazia = íntegro)."""
        problemas, anterior = [], None
        for esperado, d in enumerate(self.versoes(declaracao_id), start=1):
            if d.conteudo["versao"] != esperado:
                problemas.append(f"v{esperado}: versão ausente ou fora de ordem")
            if not verificar(d, publica):
                problemas.append(f"v{esperado}: assinatura ou hash inválido")
            if anterior is not None and d.conteudo["hash_versao_anterior"] != anterior.sha256:
                problemas.append(f"v{esperado}: não aponta para a versão anterior")
            anterior = d
        return problemas


def nova_versao(anterior: DeclaracaoAssinada, alteracoes: dict, chave: rsa.RSAPrivateKey,
                emitida_em: datetime) -> DeclaracaoAssinada:
    """Correção = nova versão encadeada. A versão anterior continua guardada e válida."""
    conteudo = {**anterior.conteudo, **alteracoes, "versao": anterior.conteudo["versao"] + 1,
                "hash_versao_anterior": anterior.sha256, "emitida_em": emitida_em}
    return assinar(conteudo, chave)
