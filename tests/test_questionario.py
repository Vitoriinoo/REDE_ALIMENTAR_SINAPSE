"""Questionário do lote (regras, seção 4.5): o que bloqueia, o que só informa, falha fechada."""

from dataclasses import replace

import pytest

from src.regras.dominio import Categoria as C
from src.regras.dominio import TipoDoador
from src.regras.questionario import Alergenico, Origem, Respostas, avaliar, perguntas_aplicaveis

OK = Respostas(origem=Origem.EXCEDENTE_PRODUCAO, embalagem_integra=True, alergenicos=frozenset({Alergenico.NENHUM}),
               requer_preparo=False, declaracao_condicoes=True)


def test_preparado_exposto_ao_consumidor_e_bloqueado():
    r = replace(OK, exposto_consumidor=True)
    assert avaliar(C.PREPARADO, TipoDoador.PJ, r) == ["EXPOSTO_AO_CONSUMIDOR"]
    assert avaliar(C.PREPARADO, TipoDoador.PJ, replace(OK, exposto_consumidor=False)) == []


def test_embalagem_violada_bloqueia_qualquer_categoria():
    assert "EMBALAGEM_VIOLADA" in avaliar(C.NAO_PERECIVEL, TipoDoador.PJ, replace(OK, embalagem_integra=False))


def test_sem_aceite_da_declaracao_legal_bloqueia():
    assert "SEM_DECLARACAO" in avaliar(C.PADARIA, TipoDoador.PJ, replace(OK, declaracao_condicoes=False))


def test_pf_precisa_de_lacre_original():
    assert avaliar(C.NAO_PERECIVEL, TipoDoador.PF, replace(OK, lacrado_original=True)) == []
    assert avaliar(C.NAO_PERECIVEL, TipoDoador.PF, replace(OK, lacrado_original=False)) == ["PF_SEM_LACRE"]


def test_pf_nao_doa_outra_categoria_mesmo_respondendo_tudo():
    r = replace(OK, lacrado_original=True, selecionado=True)
    assert "CATEGORIA_NAO_PERMITIDA_PARA_PF" in avaliar(C.HORTIFRUTI, TipoDoador.PF, r)


@pytest.mark.parametrize(("categoria", "campo", "valor", "motivo"), [
    (C.REFRIGERADO, "rotulo_visivel", False, "ROTULO_AUSENTE"),
    (C.CONGELADO, "descongelado", True, "DESCONGELADO"),
    (C.HORTIFRUTI, "selecionado", False, "HORTIFRUTI_NAO_SELECIONADO"),
])
def test_perguntas_por_categoria_bloqueiam(categoria, campo, valor, motivo):
    completas = replace(OK, rotulo_visivel=True, descongelado=False, selecionado=True)
    assert motivo in avaliar(categoria, TipoDoador.PJ, replace(completas, **{campo: valor}))


def test_resposta_obrigatoria_ausente_bloqueia_falha_fechada():
    """O sistema nunca presume que a condição sanitária é boa porque o doador não respondeu."""
    assert avaliar(C.PREPARADO, TipoDoador.PJ, OK) == ["RESPOSTA_FALTANDO:Q6"]


def test_alergenico_nenhum_nao_combina_com_outro():
    r = replace(OK, alergenicos=frozenset({Alergenico.NENHUM, Alergenico.LEITE}))
    assert "ALERGENICOS_CONTRADITORIOS" in avaliar(C.PADARIA, TipoDoador.PJ, r)


def test_alergenicos_informam_mas_nao_bloqueiam():
    r = replace(OK, alergenicos=frozenset({Alergenico.GLUTEN, Alergenico.LEITE}))
    assert avaliar(C.PADARIA, TipoDoador.PJ, r) == []


def test_perguntas_aplicaveis_dependem_da_categoria_e_do_doador():
    assert perguntas_aplicaveis(C.PREPARADO, TipoDoador.PJ) == ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
    assert perguntas_aplicaveis(C.CONGELADO, TipoDoador.PJ)[-2:] == ["Q7", "Q8"]
    assert "Q9" in perguntas_aplicaveis(C.NAO_PERECIVEL, TipoDoador.PF)
