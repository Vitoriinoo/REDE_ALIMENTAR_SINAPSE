"""Contas do login real (tabela `rede.contas`) e regras de cadastro e de entrada.

- Persistência: Supabase (`RepositorioContasPostgres`, papel `rede_api` só com SELECT e INSERT) ou
  memória com arquivo JSON local para desenvolvimento (`RepositorioContasMemoria`).
- Nada pessoal em claro: e-mail e CPF/CNPJ só como HMAC; senha só como scrypt (src/seguranca/senhas.py).
- ONG: CNPJ com dígito válido E ativo na Receita com natureza jurídica sem fins lucrativos.
- Doador PJ (regras 6.3, decisão do grupo Q14): dígito + Receita (ativo). CNAE fora do ramo de
  alimentos não bloqueia, mas a conta fica PENDENTE para revisão do admin. Doador PF: só dígito do CPF.
- Receita fora do ar ou resposta estranha → conta PENDENTE (falha fechada), que não consegue entrar.
- Bloqueio: 5 falhas seguidas no mesmo e-mail bloqueiam a entrada por 15 min, mesmo com a senha
  certa. O contador fica na memória do processo (a API roda numa instância só); reiniciar zera.
"""

from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field

from src.seguranca import senhas
from src.validacao.documentos import cnpj_valido, cpf_valido, normalizar
from src.validacao.esquemas import Email, Entrada, Nome
from src.validacao.receita import ConsultaReceita, Resultado, verificar_cnpj

MAX_FALHAS = 5
TEMPO_BLOQUEIO = timedelta(minutes=15)
PREFIXO = {"doador": "D", "ong": "O", "transportador": "V", "admin": "A"}
CAMPOS = ("codigo", "email_hash", "senha_hash", "papel", "nome", "documento_hash", "tipo_doador", "veiculo",
          "status", "criado_em")
MOTIVOS_RECEITA = {
    "digito_verificador_invalido": "CNPJ inválido (dígito verificador).",
    "cnpj_inexistente": "CNPJ não encontrado na Receita Federal.",
    "cnpj_nao_ativo": "CNPJ não está ativo na Receita Federal.",
    "natureza_juridica_incompativel_com_ong": "O CNPJ não é de entidade sem fins lucrativos (associação, fundação, "
                                              "organização religiosa ou OS).",
}


class PedidoCadastro(Entrada):
    papel: Literal["doador", "ong", "transportador"]  # admin não tem cadastro aberto (criado por script)
    email: Email
    senha: str = Field(min_length=10, max_length=128)
    nome: Nome
    documento: str = Field(min_length=11, max_length=20)
    tipo_doador: Literal["PF", "PJ"] | None = None
    veiculo: Literal["moto", "carro", "utilitario"] | None = None


class PedidoLogin(Entrada):
    email: str = Field(min_length=3, max_length=254)
    senha: str = Field(min_length=1, max_length=128)


class CadastroRecusado(ValueError):
    pass


class ContaPendente(PermissionError):
    pass


class EntradaBloqueada(PermissionError):
    pass


class CredencialInvalida(PermissionError):
    pass


# --- Persistência ------------------------------------------------------------------------------
class RepositorioContasMemoria:
    """Desenvolvimento e testes. Com `arquivo`, sobrevive a reinícios (contas demo locais)."""

    def __init__(self, arquivo: Path | None = None):
        self._arquivo = arquivo
        self._trava = threading.Lock()
        self._contas: dict[str, dict] = {}
        if arquivo and arquivo.exists():
            self._contas = {c["email_hash"]: c for c in json.loads(arquivo.read_text(encoding="utf-8"))}

    def inserir(self, conta: dict) -> None:
        with self._trava:
            if conta["email_hash"] in self._contas:
                raise CadastroRecusado("e-mail já cadastrado")
            self._contas[conta["email_hash"]] = dict(conta)
            if self._arquivo:
                self._arquivo.parent.mkdir(parents=True, exist_ok=True)
                self._arquivo.write_text(json.dumps(list(self._contas.values()), default=str), encoding="utf-8")

    def por_email_hash(self, email_hash: str) -> dict | None:
        c = self._contas.get(email_hash)
        return dict(c) if c else None

    def por_codigo(self, codigo: str) -> dict | None:
        return next((dict(c) for c in self._contas.values() if c["codigo"] == codigo), None)

    def documento_em_uso(self, papel: str, documento_hash: str) -> bool:
        return any(c["papel"] == papel and c["documento_hash"] == documento_hash for c in self._contas.values())


class RepositorioContasPostgres:
    def __init__(self, url: str):
        self._url = url

    def _conectar(self):
        import psycopg
        import psycopg.rows

        c = psycopg.connect(self._url, autocommit=True, connect_timeout=5)
        c.row_factory = psycopg.rows.dict_row
        return c

    def inserir(self, conta: dict) -> None:
        import psycopg
        from psycopg import sql

        consulta = sql.SQL("INSERT INTO rede.contas ({}) VALUES ({})").format(
            sql.SQL(", ").join(map(sql.Identifier, CAMPOS)), sql.SQL(", ").join(sql.Placeholder() * len(CAMPOS)))
        try:
            with self._conectar() as c:
                c.execute(consulta, [conta[k] for k in CAMPOS])
        except psycopg.errors.UniqueViolation:
            raise CadastroRecusado("e-mail já cadastrado") from None

    def _uma(self, onde: str, parametros: tuple) -> dict | None:
        from psycopg import sql

        with self._conectar() as c:
            return c.execute(sql.SQL("SELECT * FROM rede.contas WHERE {} LIMIT 1").format(sql.SQL(onde)),
                             parametros).fetchone()

    def por_email_hash(self, email_hash: str) -> dict | None:
        return self._uma("email_hash = %s", (email_hash,))

    def por_codigo(self, codigo: str) -> dict | None:
        return self._uma("codigo = %s", (codigo,))

    def documento_em_uso(self, papel: str, documento_hash: str) -> bool:
        return self._uma("papel = %s AND documento_hash = %s", (papel, documento_hash)) is not None


# --- Regras ------------------------------------------------------------------------------------
@dataclass
class Contas:
    repo: object
    _falhas: dict[str, tuple[int, datetime | None]] = field(default_factory=dict)
    _trava: threading.Lock = field(default_factory=threading.Lock)

    def por_email(self, email: str) -> dict | None:
        return self.repo.por_email_hash(senhas.hmac_email(email))

    def por_codigo(self, codigo: str) -> dict | None:
        return self.repo.por_codigo(codigo)

    def cadastrar(self, p: PedidoCadastro, receita: ConsultaReceita, agora: datetime | None = None) -> dict:
        doc = normalizar(p.documento)
        status = "ativa"
        if p.papel == "ong":
            if not cnpj_valido(doc):
                raise CadastroRecusado("CNPJ inválido (dígito verificador).")
            v = verificar_cnpj(doc, "ong", receita)
            if v.resultado == Resultado.REJEITADO:
                raise CadastroRecusado(MOTIVOS_RECEITA.get(v.motivo, f"CNPJ recusado: {v.motivo}"))
            status = "ativa" if v.resultado == Resultado.VALIDO else "pendente"
        elif p.papel == "doador":
            if p.tipo_doador is None:
                raise CadastroRecusado("Informe se o doador é pessoa física (PF) ou jurídica (PJ).")
            if p.tipo_doador == "PJ":
                if not cnpj_valido(doc):
                    raise CadastroRecusado("CNPJ inválido (dígito verificador).")
                v = verificar_cnpj(doc, "doador", receita)
                if v.resultado == Resultado.REJEITADO:
                    raise CadastroRecusado(MOTIVOS_RECEITA.get(v.motivo, f"CNPJ recusado: {v.motivo}"))
                status = "ativa" if v.resultado == Resultado.VALIDO else "pendente"  # REVISAO_ADMIN ou PENDENTE
            if p.tipo_doador == "PF" and not cpf_valido(doc):
                raise CadastroRecusado("CPF inválido (dígito verificador).")
        else:  # transportador
            if p.veiculo is None:
                raise CadastroRecusado("Informe o veículo: moto, carro ou utilitario.")
            if not cpf_valido(doc):
                raise CadastroRecusado("CPF inválido (dígito verificador).")

        documento_hash = senhas.hmac_documento(doc)
        if self.repo.documento_em_uso(p.papel, documento_hash):
            raise CadastroRecusado("Já existe uma conta deste papel com este documento.")
        conta = {
            "codigo": f"{PREFIXO[p.papel]}-C{secrets.token_hex(4).upper()}",
            "email_hash": senhas.hmac_email(p.email), "senha_hash": senhas.gerar_hash(p.senha), "papel": p.papel,
            "nome": p.nome, "documento_hash": documento_hash,
            "tipo_doador": p.tipo_doador if p.papel == "doador" else None,
            "veiculo": p.veiculo if p.papel == "transportador" else None,
            "status": status, "criado_em": agora or datetime.now(timezone.utc),
        }
        if self.repo.por_email_hash(conta["email_hash"]):
            raise CadastroRecusado("e-mail já cadastrado")
        self.repo.inserir(conta)
        return conta

    def entrar(self, email: str, senha: str, agora: datetime | None = None) -> dict:
        agora = agora or datetime.now(timezone.utc)
        chave = senhas.hmac_email(email)
        with self._trava:
            falhas, ate = self._falhas.get(chave, (0, None))
            if ate and agora < ate:
                raise EntradaBloqueada("muitas tentativas: tente de novo em alguns minutos")
        conta = self.repo.por_email_hash(chave)
        # Confere a senha mesmo sem conta (hash fictício): o tempo de resposta não revela se o e-mail existe.
        ok = senhas.conferir(senha, conta["senha_hash"] if conta else _HASH_FICTICIO)
        if not (conta and ok):
            with self._trava:
                falhas = (0 if ate else falhas) + 1
                self._falhas[chave] = (falhas, agora + TEMPO_BLOQUEIO if falhas >= MAX_FALHAS else None)
            raise CredencialInvalida("e-mail ou senha inválidos")
        with self._trava:
            self._falhas.pop(chave, None)
        if conta["status"] != "ativa":
            raise ContaPendente("conta pendente: aguardando a verificação do CNPJ na Receita Federal "
                                "ou a revisão do admin")
        return conta


_HASH_FICTICIO = senhas.gerar_hash(secrets.token_urlsafe(16))
