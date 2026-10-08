"""Gera uma Declaração de Doação de exemplo (JSON assinado + PDF) para demonstração.

Fluxo completo do cadastro, sem API: esquema de entrada -> regras -> questionário ->
declaração assinada (RSA-PSS) -> repositório só de inclusão -> PDF. Em seguida
simula uma adulteração e mostra a verificação falhando.

A chave privada de exemplo fica em `segredos/` (fora do Git); a pública vai para
`docs/exemplos/` para qualquer um verificar.

Uso:
    python -m src.seguranca.exemplo_declaracao
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization

from src.data.curadoria_ipvs import RAIZ
from src.regras.dominio import TipoDoador
from src.regras.questionario import avaliar
from src.regras.validade import em_rota_expressa, validade_efetiva
from src.seguranca.declaracao import (
    DeclaracaoAssinada,
    RepositorioDeclaracoes,
    assinar,
    gerar_chave_privada,
    montar_conteudo,
    salvar_par_de_chaves,
    verificar,
)
from src.seguranca.declaracao_pdf import gerar_pdf
from src.seguranca.minimizacao import pseudonimo
from src.validacao.esquemas import CadastroLote

PRIVADA = RAIZ / "segredos" / "chave-declaracao-exemplo.pem"
PUBLICA = RAIZ / "docs" / "exemplos" / "chave-publica-exemplo.pem"


def _chave():
    if PRIVADA.exists():
        return serialization.load_pem_private_key(PRIVADA.read_bytes(), password=None)
    chave = gerar_chave_privada()
    salvar_par_de_chaves(chave, PRIVADA, PUBLICA)
    return chave


def main() -> None:
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    entrada = {
        "descricao": "30 marmitas de arroz, feijão e frango feitas hoje no almoço. Dúvidas: ligar (11) 98765-4321",
        "categoria": "preparado", "armazenamento": "refrigerado", "peso_kg": 12.5,
        "preparo": (agora - timedelta(hours=3)).isoformat(),
        "questionario": {"origem": "excedente_producao", "embalagem_integra": True,
                         "alergenicos": ["gluten", "leite"], "requer_preparo": False,
                         "declaracao_condicoes": True, "exposto_consumidor": False},
    }
    lote = CadastroLote.model_validate(entrada, context={"agora": agora})  # camada 1: esquema
    respostas = lote.questionario.para_regra()
    motivos = avaliar(lote.categoria, TipoDoador.PJ, respostas)  # camada 4: regra
    validade = validade_efetiva(lote.categoria, lote.armazenamento, preparo=lote.preparo)

    conteudo = montar_conteudo(
        lote_id="L-000001", doador_pseudonimo=pseudonimo("doador", "D-0001"), tipo_doador=TipoDoador.PJ,
        categoria=lote.categoria, armazenamento=lote.armazenamento, peso_kg=lote.peso_kg,
        descricao=lote.descricao, validade_efetiva=validade, base_validade={"preparo": lote.preparo},
        rota_expressa=em_rota_expressa(lote.categoria, lote.armazenamento), respostas=respostas,
        motivos_bloqueio=motivos,
        sugestao_ia={"categoria": "preparado", "confianca": 0.97, "modelo": "nlp-similaridade-v1"},
        emitida_em=agora,
    )
    chave = _chave()
    declaracao = assinar(conteudo, chave)
    repo = RepositorioDeclaracoes(RAIZ / "var" / "declaracoes")
    repo.salvar(declaracao)
    pdf = gerar_pdf(declaracao, RAIZ / "docs" / "exemplos" / "declaracao-exemplo.pdf")

    publica = chave.public_key()
    adulterada = copy.deepcopy(declaracao.conteudo)
    adulterada["questionario"]["Q6"]["resposta"] = True  # alguém troca uma resposta depois de assinada
    falsa = DeclaracaoAssinada(adulterada, declaracao.sha256, declaracao.assinatura, declaracao.algoritmo,
                               declaracao.chave_id)
    print(f"Resultado do cadastro: {conteudo['resultado']} {motivos or ''}")
    print(f"Descrição como ficou registrada: {conteudo['alimento']['descricao']}")
    print(f"SHA-256: {declaracao.sha256}")
    print(f"Assinatura válida: {verificar(declaracao, publica)}")
    print(f"Assinatura válida depois de adulterar a resposta Q6: {verificar(falsa, publica)}")
    print(f"PDF: {pdf.relative_to(RAIZ)}  ·  chave pública: {PUBLICA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
