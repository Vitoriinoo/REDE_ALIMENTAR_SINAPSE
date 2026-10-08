"""Validação de entrada (regras 4.6): tudo que entra é validado antes de ser considerado."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.validacao.esquemas import CadastroDoador, CadastroLote, CadastroOng, PedidoOng, RespostaOferta

AGORA = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
CTX = {"agora": AGORA}

QUESTIONARIO = {"origem": "excedente_producao", "embalagem_integra": True, "alergenicos": ["nenhum"],
                "requer_preparo": False, "declaracao_condicoes": True, "exposto_consumidor": False}
LOTE = {"descricao": "30 marmitas de arroz, feijão e frango", "categoria": "preparado", "armazenamento": "ambiente",
        "peso_kg": 8, "preparo": "2026-10-05T14:00:00Z", "questionario": QUESTIONARIO}
ONG = {"nome": "Associação Prato Cheio", "email": "contato@pratocheio.org.br", "telefone": "+5511987654321",
       "cep": "08410000", "lat": -23.54, "lon": -46.40, "cnpj": "12.ABC.345/01DE-35", "capacidade_kg_dia": 80,
       "capacidade_refrigerada_kg": 20, "tem_refrigeracao": True, "tem_freezer": False, "tem_cozinha": True,
       "distribui_cestas": False, "pode_buscar": True, "abertura_h": 8, "fechamento_h": 18, "turnos": ["almoco"],
       "categorias_aceitas": ["preparado", "refrigerado", "nao_perecivel"]}
DOADOR = {"nome": "Restaurante Bom Prato", "email": "doacoes@bomprato.com.br", "telefone": "+551133334444",
          "cep": "01310100", "lat": -23.56, "lon": -46.65, "tipo": "PJ", "documento": "11.222.333/0001-81",
          "pode_entregar": False, "tem_refrigeracao": True}


def _rejeita(modelo, dados, **kw):
    with pytest.raises(ValidationError):
        modelo.model_validate(dados, **kw)


def test_lote_valido_passa_inclusive_vindo_como_json():
    assert CadastroLote.model_validate(LOTE, context=CTX).peso_kg == 8.0
    assert CadastroLote.model_validate_json(json.dumps(LOTE), context=CTX).categoria == "preparado"


@pytest.mark.parametrize("alteracao", [
    {"aprovado": True},  # campo desconhecido: ninguém injeta flag de aprovação
    {"peso_kg": "8"},  # tipo estrito: texto não vira número
    {"peso_kg": float("nan")},
    {"peso_kg": 0.1},
    {"peso_kg": 50_000},
    {"categoria": "bebida_alcoolica"},  # fora da lista fechada
    {"preparo": "2026-10-05T14:00:00"},  # data sem fuso
    {"preparo": "2026-10-06T14:00:00Z"},  # no futuro
    {"preparo": "2026-09-30T14:00:00Z"},  # mais de 72 h atrás
    {"descricao": "marmitas​ grátis"},  # caractere invisível
    {"descricao": "x" * 501},
    {"armazenamento": "congelado"},  # não se aplica a preparado
    {"validade_informada": "2026-10-09T00:00:00Z"},  # campo que não se aplica à categoria
])
def test_lote_invalido_e_rejeitado(alteracao):
    _rejeita(CadastroLote, LOTE | alteracao, context=CTX)


def test_categoria_exige_os_campos_de_validade_certos():
    refrigerado = LOTE | {"categoria": "refrigerado", "armazenamento": "ambiente", "preparo": None,
                          "validade_rotulo": "2026-10-10T00:00:00Z"}
    _rejeita(CadastroLote, refrigerado, context=CTX)  # fora da geladeira exige a hora em que saiu
    ok = refrigerado | {"saida_refrigeracao": "2026-10-05T14:30:00Z",
                        "questionario": QUESTIONARIO | {"exposto_consumidor": None, "rotulo_visivel": True}}
    assert CadastroLote.model_validate(ok, context=CTX).saida_refrigeracao is not None


def test_questionario_rejeita_resposta_em_texto():
    _rejeita(CadastroLote, LOTE | {"questionario": QUESTIONARIO | {"embalagem_integra": "sim"}}, context=CTX)


def test_ong_valida_e_coerencias_da_estrutura():
    assert CadastroOng.model_validate(ONG).pode_buscar
    _rejeita(CadastroOng, ONG | {"categorias_aceitas": ["congelado"]})  # sem freezer
    _rejeita(CadastroOng, ONG | {"tem_freezer": True, "tem_refrigeracao": False, "capacidade_refrigerada_kg": 0})
    _rejeita(CadastroOng, ONG | {"abertura_h": 19})
    _rejeita(CadastroOng, ONG | {"capacidade_refrigerada_kg": 500})
    _rejeita(CadastroOng, ONG | {"cnpj": "12.ABC.345/01DE-36"})
    _rejeita(CadastroOng, ONG | {"lat": -22.9})  # fora do recorte (Campinas)
    _rejeita(CadastroOng, ONG | {"email": "nao-e-email"})
    _rejeita(CadastroOng, ONG | {"telefone": "11987654321"})  # sem +55


def test_doador_valida_documento_conforme_o_tipo():
    assert CadastroDoador.model_validate(DOADOR).documento_normalizado == "11222333000181"
    _rejeita(CadastroDoador, DOADOR | {"tipo": "PF"})  # CNPJ não serve como CPF
    assert CadastroDoador.model_validate(DOADOR | {"tipo": "PF", "documento": "529.982.247-25"}).tipo == "PF"


def test_pedido_e_resposta_de_oferta():
    assert PedidoOng.model_validate({"categoria": "nao_perecivel", "kg": 40, "validade_dias": 5}).kg == 40
    _rejeita(PedidoOng, {"categoria": "nao_perecivel", "kg": 40, "validade_dias": 10})
    _rejeita(RespostaOferta, {"lote_id": "L-000123", "aceita": False})  # recusa exige motivo
    _rejeita(RespostaOferta, {"lote_id": "../../etc", "aceita": True})
