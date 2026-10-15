"""Senha com scrypt, documento e e-mail só como HMAC, token de sessão `ras_` assinado com HMAC."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.seguranca import senhas


def test_hash_de_senha_confere_e_nunca_guarda_a_senha():
    h = senhas.gerar_hash("uma-senha-forte-123")
    assert h.startswith("scrypt$") and "uma-senha-forte-123" not in h
    assert senhas.conferir("uma-senha-forte-123", h)
    assert not senhas.conferir("uma-senha-forte-124", h)


def test_mesma_senha_gera_hashes_diferentes_por_causa_do_sal():
    assert senhas.gerar_hash("mesma-senha-123") != senhas.gerar_hash("mesma-senha-123")


def test_hash_corrompido_nao_confere_nem_quebra():
    assert not senhas.conferir("qualquer", "scrypt$lixo")
    assert not senhas.conferir("qualquer", "")


def test_documento_vira_hmac_independente_da_mascara():
    a = senhas.hmac_documento("11.222.333/0001-81")
    assert a == senhas.hmac_documento("11222333000181")
    assert len(a) == 64 and "11222333" not in a


def test_email_vira_hmac_sem_diferenca_de_caixa_ou_espaco():
    assert senhas.hmac_email(" Maria@Exemplo.com ") == senhas.hmac_email("maria@exemplo.com")


def test_token_ida_e_volta():
    agora = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    token, expira = senhas.emitir_token("ong", "O-005", agora=agora)
    assert token.startswith("ras_") and expira == agora + senhas.VALIDADE_TOKEN
    assert senhas.ler_token(token, agora=agora + timedelta(hours=1)) == {"papel": "ong", "id": "O-005"}


def test_token_expirado_ou_adulterado_e_recusado():
    agora = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    token, _ = senhas.emitir_token("doador", "D-0008", agora=agora)
    assert senhas.ler_token(token, agora=agora + senhas.VALIDADE_TOKEN + timedelta(seconds=1)) is None
    corpo, assinatura = token.removeprefix("ras_").split(".")
    outro, _ = senhas.emitir_token("admin", "A-01", agora=agora)
    corpo_admin = outro.removeprefix("ras_").split(".")[0]
    assert senhas.ler_token(f"ras_{corpo_admin}.{assinatura}", agora=agora) is None  # troca de papel
    assert senhas.ler_token(f"ras_{corpo}.xx", agora=agora) is None
    assert senhas.ler_token("ras_lixo", agora=agora) is None
    assert senhas.ler_token("ra_doador_x", agora=agora) is None
