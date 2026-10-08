"""Verificação do CNPJ na Receita (regras 6.3): resposta externa também é entrada não confiável."""

from src.validacao.receita import ConsultaSimulada, Resultado, verificar_cnpj

ONG = "11222333000181"
RESTAURANTE = "12ABC34501DE35"


def _resp(cnpj, situacao=2, natureza=3999, cnae=8800600, **extra):
    return {"cnpj": cnpj, "situacao_cadastral": situacao, "descricao_situacao_cadastral": "ATIVA" if situacao == 2 else "BAIXADA",
            "codigo_natureza_juridica": natureza, "cnae_fiscal": cnae, **extra}


def test_ong_ativa_sem_fins_lucrativos_e_valida():
    base = ConsultaSimulada({ONG: _resp(ONG, qsa=[{"nome_socio": "FULANO"}])})
    v = verificar_cnpj("11.222.333/0001-81", "ong", base)
    assert v.resultado == Resultado.VALIDO


def test_empresa_com_fins_lucrativos_nao_vira_ong():
    v = verificar_cnpj(ONG, "ong", ConsultaSimulada({ONG: _resp(ONG, natureza=2062)}))
    assert v.resultado == Resultado.REJEITADO and v.motivo == "natureza_juridica_incompativel_com_ong"


def test_cnpj_baixado_e_rejeitado():
    v = verificar_cnpj(ONG, "ong", ConsultaSimulada({ONG: _resp(ONG, situacao=8)}))
    assert v.resultado == Resultado.REJEITADO and v.motivo == "cnpj_nao_ativo"


def test_digito_errado_nem_consulta_a_receita():
    class Explode:
        nome = "explode"

        def consultar(self, cnpj):
            raise AssertionError("não deveria consultar")

    assert verificar_cnpj("11.222.333/0001-82", "ong", Explode()).motivo == "digito_verificador_invalido"


def test_doador_fora_do_ramo_de_alimentos_vai_para_revisao():
    base = {RESTAURANTE: _resp(RESTAURANTE, natureza=2062, cnae=5611201)}
    assert verificar_cnpj(RESTAURANTE, "doador", ConsultaSimulada(base)).resultado == Resultado.VALIDO
    base = {RESTAURANTE: _resp(RESTAURANTE, natureza=2062, cnae=6201501)}  # desenvolvimento de software
    assert verificar_cnpj(RESTAURANTE, "doador", ConsultaSimulada(base)).resultado == Resultado.REVISAO_ADMIN


def test_receita_fora_do_ar_deixa_pendente_falha_fechada():
    v = verificar_cnpj(ONG, "ong", ConsultaSimulada({}, indisponivel=True))
    assert v.resultado == Resultado.PENDENTE


def test_resposta_fora_do_esquema_deixa_pendente():
    v = verificar_cnpj(ONG, "ong", ConsultaSimulada({ONG: {"cnpj": ONG, "situacao_cadastral": "ATIVA"}}))
    assert v.resultado == Resultado.PENDENTE and v.motivo == "resposta_fora_do_esquema"


def test_resposta_de_outro_cnpj_nao_e_aceita():
    v = verificar_cnpj(ONG, "ong", ConsultaSimulada({ONG: _resp(RESTAURANTE)}))
    assert v.resultado == Resultado.PENDENTE


def test_cnpj_inexistente_e_rejeitado():
    assert verificar_cnpj(ONG, "ong", ConsultaSimulada({})).motivo == "cnpj_inexistente"
