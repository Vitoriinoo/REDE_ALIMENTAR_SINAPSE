"""Declaração de Doação (regras 4.5): assinada, verificável, imutável e versionada."""

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from src.regras.dominio import Armazenamento, Categoria, TipoDoador
from src.regras.questionario import Alergenico, Origem, Respostas
from src.seguranca.declaracao import (
    DeclaracaoAssinada,
    RepositorioDeclaracoes,
    assinar,
    gerar_chave_privada,
    json_canonico,
    montar_conteudo,
    nova_versao,
    verificar,
)
from src.seguranca.declaracao_pdf import gerar_pdf

AGORA = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def chave():
    return gerar_chave_privada()


def _conteudo(**kw):
    respostas = Respostas(origem=Origem.EXCEDENTE_PRODUCAO, embalagem_integra=True,
                          alergenicos=frozenset({Alergenico.GLUTEN, Alergenico.LEITE}), requer_preparo=False,
                          declaracao_condicoes=True, exposto_consumidor=False)
    base = dict(lote_id="L-000123", doador_pseudonimo="doador:3f9a1c0b2d4e5f60", tipo_doador=TipoDoador.PJ,
                categoria=Categoria.PREPARADO, armazenamento=Armazenamento.AMBIENTE, peso_kg=8.0,
                descricao="30 marmitas; dúvidas: joao@exemplo.com ou (11) 98765-4321",
                validade_efetiva=AGORA + timedelta(hours=2), base_validade={"preparo": AGORA - timedelta(hours=1)},
                rota_expressa=True, respostas=respostas, motivos_bloqueio=[],
                sugestao_ia={"categoria": "preparado", "confianca": 0.93, "modelo": "nlp-similaridade-v1"},
                emitida_em=AGORA)
    return montar_conteudo(**(base | kw))


def test_assinatura_valida_e_conteudo_alterado_e_detectado(chave):
    d = assinar(_conteudo(), chave)
    assert verificar(d, chave.public_key())
    adulterado = copy.deepcopy(d.conteudo)
    adulterado["alimento"]["peso_kg"] = 80.0
    assert not verificar(DeclaracaoAssinada(adulterado, d.sha256, d.assinatura, d.algoritmo, d.chave_id),
                         chave.public_key())


def test_assinatura_de_outra_chave_nao_vale(chave):
    d = assinar(_conteudo(), chave)
    assert not verificar(d, gerar_chave_privada().public_key())


def test_json_canonico_e_estavel():
    a = {"b": 1, "a": {"y": [3, 1], "x": "ç"}}
    b = {"a": {"x": "ç", "y": [3, 1]}, "b": 1}
    assert json_canonico(a) == json_canonico(b) == '{"a":{"x":"ç","y":[3,1]},"b":1}'.encode()


def test_dado_pessoal_digitado_no_texto_vai_mascarado():
    descricao = _conteudo()["alimento"]["descricao"]
    assert "joao@" not in descricao and "98765" not in descricao and "[EMAIL]" in descricao


def test_bloqueada_tambem_e_documento(chave):
    d = assinar(_conteudo(motivos_bloqueio=["EXPOSTO_AO_CONSUMIDOR"]), chave)
    assert d.conteudo["resultado"] == "BLOQUEADA" and verificar(d, chave.public_key())


def test_repositorio_so_inclui_e_versoes_sao_encadeadas(tmp_path, chave):
    repo = RepositorioDeclaracoes(tmp_path)
    v1 = assinar(_conteudo(), chave)
    repo.salvar(v1)
    with pytest.raises(FileExistsError):  # imutável: não sobrescreve
        repo.salvar(v1)
    v2 = nova_versao(v1, {"motivos_bloqueio": ["EMBALAGEM_VIOLADA"], "resultado": "BLOQUEADA"}, chave,
                     AGORA + timedelta(minutes=5))
    repo.salvar(v2)
    assert repo.verificar_historico(v1.conteudo["declaracao_id"], chave.public_key()) == []
    assert repo.ler(v1.conteudo["declaracao_id"], 1).sha256 == v1.sha256  # a versão anterior continua lá


def test_historico_adulterado_e_detectado(tmp_path, chave):
    repo = RepositorioDeclaracoes(tmp_path)
    v1 = assinar(_conteudo(), chave)
    caminho = repo.salvar(v1)
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["conteudo"]["alimento"]["peso_kg"] = 1.0
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    assert repo.verificar_historico(v1.conteudo["declaracao_id"], chave.public_key())


def test_id_de_declaracao_nao_permite_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        RepositorioDeclaracoes(tmp_path).ler("../../segredos", 1)


def test_pdf_legivel_e_gerado_com_o_json_ao_lado(tmp_path, chave):
    d = assinar(_conteudo(), chave)
    pdf = gerar_pdf(d, tmp_path / "declaracao.pdf")
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.with_suffix(".json").exists()
