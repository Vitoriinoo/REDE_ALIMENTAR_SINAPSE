"""Camada de controle da IA (regras 10.3): desligamento, piso de segurança, saída validada, log."""

from datetime import datetime, timedelta, timezone

import numpy as np

from src.models.controle import ControleIA, Fonte, Interruptores, ModeloIA
from src.observabilidade.registro import RegistroAuditavel, Trilha
from src.regras.dominio import Armazenamento as A
from src.regras.dominio import Categoria as C
from src.regras.dominio import Prioridade, TipoDoador

h = lambda n: timedelta(hours=n)  # noqa: E731


class ModeloFixo:
    """Dublê de modelo: sempre devolve a mesma classe/probabilidade."""

    def __init__(self, classe="BAIXA", prob=0.9):
        self.classe, self.prob = classe, prob

    def predict(self, x):
        return np.array([self.classe] * len(x))

    def predict_proba(self, x):
        return np.array([[1 - self.prob, self.prob]] * len(x))


class ModeloQuebrado:
    def predict(self, x):
        raise RuntimeError("artefato corrompido")

    predict_proba = predict


def _controle(tmp_path, m1=None, m2=None, desligados=()):
    reg = RegistroAuditavel(tmp_path, chave=b"k")
    inter = Interruptores(registro=reg)
    for m in desligados:
        inter.definir(m, False, ator="admin:1", motivo="teste")
    return ControleIA(interruptores=inter, registro=reg, m1=m1, m1_meta={"versao": "prioridade-teste"},
                      m2=m2, m2_meta={"versao": "descarte-teste", "limiar": 0.5}), reg


def _m2_entradas(**kw):
    return {"categoria": "preparado", "armazenamento": "refrigerado", "tipo_doador": "PJ", "segmento": "restaurante",
            "regiao": "SP - Centro", "prioridade": "ALTA", "horas_restantes": 30.0, "peso_kg": 8.0, "hora": 15,
            "dia_semana": 2, "n_ongs_compativeis_10km": 4, "dist_ong_top_km": 3.0, "n_transportadores_ativos_raio": 6,
            "min_ate_receber_top": 15.0, "rota_expressa": False, "doador_tem_refrigeracao": True,
            "fim_de_semana": False, "feriado": False, "refrigerado_disponivel": True, "doador_pode_entregar": False,
            "requer_preparo": False} | kw


def test_piso_de_seguranca_o_modelo_nao_baixa_um_caso_critico(tmp_path):
    controle, _ = _controle(tmp_path, m1=ModeloFixo("BAIXA"))
    rec = controle.prioridade(C.PREPARADO, A.AMBIENTE, TipoDoador.PJ, h(2), 8, ator="doador:x")  # rota expressa
    assert rec.valor == Prioridade.CRITICA and rec.fonte == Fonte.PISO_DE_SEGURANCA


def test_o_modelo_pode_subir_a_urgencia(tmp_path):
    controle, _ = _controle(tmp_path, m1=ModeloFixo("ALTA"))
    rec = controle.prioridade(C.NAO_PERECIVEL, A.AMBIENTE, TipoDoador.PJ, timedelta(days=40), 5, ator="doador:x")
    assert rec.valor == Prioridade.ALTA and rec.fonte == Fonte.MODELO


def test_modelo_desligado_a_regra_assume_e_fica_registrado(tmp_path):
    controle, reg = _controle(tmp_path, m1=ModeloFixo("ALTA"), desligados=[ModeloIA.PRIORIDADE])
    rec = controle.prioridade(C.NAO_PERECIVEL, A.AMBIENTE, TipoDoador.PJ, timedelta(days=40), 5, ator="doador:x")
    assert rec.fonte == Fonte.REGRA and rec.valor == Prioridade.BAIXA
    acoes = [r["acao"] for r in reg.ler(Trilha.AUDITORIA)]
    assert acoes == ["DESLIGAR_MODELO", "PREDICAO_PRIORIDADE"]


def test_saida_fora_da_lista_fechada_cai_na_regra(tmp_path):
    controle, _ = _controle(tmp_path, m1=ModeloFixo("URGENTISSIMO"))
    rec = controle.prioridade(C.HORTIFRUTI, A.AMBIENTE, TipoDoador.PJ, h(30), 5, ator="doador:x")
    assert rec.fonte == Fonte.REGRA and rec.motivo_fallback == "erro:ValueError"


def test_erro_no_modelo_nao_derruba_o_sistema(tmp_path):
    controle, _ = _controle(tmp_path, m1=ModeloQuebrado(), m2=ModeloQuebrado())
    assert controle.prioridade(C.HORTIFRUTI, A.AMBIENTE, TipoDoador.PJ, h(30), 5, ator="x").fonte == Fonte.REGRA
    assert controle.risco_descarte(_m2_entradas(), ator="x").fonte == Fonte.REGRA


def test_probabilidade_invalida_cai_na_heuristica(tmp_path):
    controle, _ = _controle(tmp_path, m2=ModeloFixo(prob=1.7))
    rec = controle.risco_descarte(_m2_entradas(horas_restantes=2.0), ator="x")
    assert rec.fonte == Fonte.REGRA and rec.valor is True  # heurística: faltam < 4 h para o limite


def test_m2_usa_o_limiar_dos_metadados(tmp_path):
    controle, _ = _controle(tmp_path, m2=ModeloFixo(prob=0.62))
    rec = controle.risco_descarte(_m2_entradas(), ator="x")
    assert rec.valor is True and rec.confianca == 0.62 and rec.fonte == Fonte.MODELO


def test_toda_chamada_de_ia_vai_para_a_auditoria_com_contexto(tmp_path):
    controle, reg = _controle(tmp_path, m1=ModeloFixo("MEDIA"))
    controle.prioridade(C.HORTIFRUTI, A.AMBIENTE, TipoDoador.PJ, h(100), 5, ator="doador:x", recurso="lote:L-000001")
    r = reg.ler(Trilha.AUDITORIA)[-1]
    assert r["acao"] == "PREDICAO_PRIORIDADE" and r["recurso"] == "lote:L-000001"
    assert {"entradas", "saida", "fonte", "modelo_versao", "latencia_ms", "prioridade_regra"} <= set(r["detalhes"])
    assert reg.verificar_cadeia() == []


def test_nlp_desligado_doador_escolhe_sozinho(tmp_path):
    controle, reg = _controle(tmp_path, desligados=[ModeloIA.NLP])
    assert controle.sugerir_categoria("30 marmitas", ator="doador:x") is None
    detalhes = reg.ler(Trilha.AUDITORIA)[-1]["detalhes"]
    assert "30 marmitas" not in str(detalhes) and "texto_resumo" in detalhes["entradas"]


def test_desligamento_sobrevive_a_reinicio(tmp_path):
    arquivo = tmp_path / "ia.json"
    Interruptores(arquivo).definir(ModeloIA.DESCARTE, False, ator="admin:1", motivo="drift")
    assert not Interruptores(arquivo).ligado(ModeloIA.DESCARTE)
