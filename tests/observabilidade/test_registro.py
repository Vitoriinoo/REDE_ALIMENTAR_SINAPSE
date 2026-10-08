"""Logs (regras 10.1): cobertura completa, conteúdo mínimo, cadeia de HMAC e retenção."""

import json
from datetime import datetime, timedelta, timezone

from src.observabilidade.registro import RegistroAuditavel, Resultado, Trilha
from src.seguranca.minimizacao import minimizar, pseudonimo

CHAVE = b"chave-de-teste"


class Relogio:
    def __init__(self, inicio):
        self.agora = inicio

    def __call__(self):
        return self.agora


def _registro(tmp_path, relogio=None):
    return RegistroAuditavel(tmp_path, chave=CHAVE, relogio=relogio or (lambda: datetime(2026, 10, 5, tzinfo=timezone.utc)))


def _decisao(reg, n=1):
    for i in range(n):
        reg.registrar(Trilha.AUDITORIA, componente="matching", acao="ACEITE_ONG", ator=pseudonimo("ong", f"O-{i}"),
                      papel="ong", recurso=f"lote:L-{i:06d}")


def test_dado_pessoal_nunca_vai_para_o_log(tmp_path):
    reg = _registro(tmp_path)
    reg.registrar(Trilha.OPERACIONAL, componente="api", acao="VALIDACAO_REJEITADA", ator="doador:abc", papel="doador",
                  resultado=Resultado.NEGADO,
                  detalhes={"cpf": "529.982.247-25", "campo": "peso_kg", "obs": "ligar 11 98765-4321 ou a@b.com",
                            "aninhado": {"email": "x@y.com", "regra": "faixa"}})
    linha = (tmp_path / "operacional-2026-10-05.jsonl").read_text(encoding="utf-8")
    for segredo in ("529.982.247-25", "98765", "a@b.com", "x@y.com"):
        assert segredo not in linha
    assert '"campo": "peso_kg"' in linha and "[TELEFONE]" in linha


def test_cadeia_integra_e_continua_apos_reinicio(tmp_path):
    reg = _registro(tmp_path)
    _decisao(reg, 3)
    reg2 = _registro(tmp_path)  # reinício do processo: recupera o último hash
    _decisao(reg2, 2)
    assert reg2.verificar_cadeia() == []
    assert len(reg2.ler(Trilha.AUDITORIA)) == 5


def test_alterar_linha_e_detectado(tmp_path):
    reg = _registro(tmp_path)
    _decisao(reg, 3)
    arq = tmp_path / "auditoria-2026-10.jsonl"
    linhas = arq.read_text(encoding="utf-8").splitlines()
    r = json.loads(linhas[1])
    r["resultado"] = "negado"
    linhas[1] = json.dumps(r)
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    assert any("HMAC não confere" in p for p in reg.verificar_cadeia())


def test_apagar_linha_e_detectado(tmp_path):
    reg = _registro(tmp_path)
    _decisao(reg, 3)
    arq = tmp_path / "auditoria-2026-10.jsonl"
    linhas = arq.read_text(encoding="utf-8").splitlines()
    arq.write_text("\n".join([linhas[0], linhas[2]]) + "\n", encoding="utf-8")
    assert any("elo quebrado" in p for p in reg.verificar_cadeia())


def test_sem_a_chave_nao_da_para_refazer_a_cadeia(tmp_path):
    """Quem escreve no arquivo mas não tem a chave não recalcula os HMACs."""
    _decisao(RegistroAuditavel(tmp_path, chave=b"chave-do-atacante"), 2)
    assert RegistroAuditavel(tmp_path, chave=CHAVE).verificar_cadeia()


def test_retencao_apaga_so_o_vencido_e_preserva_a_cadeia(tmp_path):
    relogio = Relogio(datetime(2020, 1, 15, tzinfo=timezone.utc))
    reg = _registro(tmp_path, relogio)
    _decisao(reg, 2)
    reg.registrar(Trilha.OPERACIONAL, componente="api", acao="ACESSO", ator="x", papel="anonimo")
    relogio.agora = datetime(2026, 10, 5, tzinfo=timezone.utc)
    _decisao(reg, 2)
    reg.registrar(Trilha.OPERACIONAL, componente="api", acao="ACESSO", ator="x", papel="anonimo")

    removidos = reg.aplicar_retencao()
    assert removidos == ["operacional-2020-01-15.jsonl", "auditoria-2020-01.jsonl"] or set(removidos) == {
        "operacional-2020-01-15.jsonl", "auditoria-2020-01.jsonl"}
    assert reg.verificar_cadeia() == []  # a âncora selada mantém a cadeia verificável


def test_ancora_forjada_e_detectada(tmp_path):
    relogio = Relogio(datetime(2020, 1, 15, tzinfo=timezone.utc))
    reg = _registro(tmp_path, relogio)
    _decisao(reg, 1)
    relogio.agora = datetime(2026, 10, 5, tzinfo=timezone.utc)
    _decisao(reg, 1)
    reg.aplicar_retencao()
    ancora = json.loads((tmp_path / "auditoria-ancora.json").read_text())
    ancora["hash"] = "f" * 64
    (tmp_path / "auditoria-ancora.json").write_text(json.dumps(ancora))
    assert reg.verificar_cadeia()


def test_minimizar_remove_chaves_proibidas_recursivamente():
    assert minimizar({"nome": "Ana", "x": [{"telefone": "1"}, {"ok": 1}]}) == {"x": [{}, {"ok": 1}]}


def test_pseudonimo_e_estavel_e_nao_revela_o_id():
    p = pseudonimo("doador", "D-0001")
    assert p == pseudonimo("doador", "D-0001") and "D-0001" not in p and p.startswith("doador:")
