"""Catálogo de dados: classificação, base legal (LGPD), retenção e dono de CADA coluna.

Governança que o código cobra (regras, seção 11): `tests/test_governanca.py` falha se
um arquivo de dados ganhar uma coluna que não está classificada aqui. Assim, ninguém
adiciona um dado novo sem decidir para que ele serve, quem responde por ele e por
quanto tempo fica guardado.

Inventário em texto (registro de tratamento, LGPD art. 37): docs/governanca/inventario-de-dados.md
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Classe(StrEnum):
    PUBLICA = "publica"  # dado público de referência (IBGE, SEADE)
    INTERNA = "interna"  # operacional, não identifica pessoa
    PSEUDONIMIZADA = "pessoal_pseudonimizada"  # identifica indiretamente (id, hash HMAC, localização de PF)
    TEXTO_LIVRE = "pessoal_potencial"  # texto digitado: pode conter dado pessoal sem querer


class BaseLegal(StrEnum):
    NAO_SE_APLICA = "não se aplica (sem dado pessoal)"
    CONTRATO = "execução de contrato / procedimentos preliminares (LGPD art. 7º, V)"
    LEGITIMO_INTERESSE = "legítimo interesse: segurança, prevenção a fraude e melhoria do serviço (art. 7º, IX)"
    EXERCICIO_DE_DIREITOS = "exercício regular de direitos: trilha de auditoria (art. 7º, VI)"


class Retencao(StrEnum):
    PERMANENTE = "enquanto a fonte pública existir"
    OPERACIONAL_90D = "90 dias"
    CONTATO_12M = "12 meses após a última atividade, depois anonimizado"
    AUDITORIA_5A = "5 anos (prazo do CDC art. 27, por analogia)"


class Dono(StrEnum):
    DADOS = "responsável por dados"
    PRODUTO = "responsável por produto/operação"
    IA = "responsável pelos modelos de IA"
    SEGURANCA = "responsável por segurança"


@dataclass(frozen=True)
class Campo:
    classe: Classe
    base_legal: BaseLegal
    retencao: Retencao
    dono: Dono


PUB = Campo(Classe.PUBLICA, BaseLegal.NAO_SE_APLICA, Retencao.PERMANENTE, Dono.DADOS)
INT_OPER = Campo(Classe.INTERNA, BaseLegal.NAO_SE_APLICA, Retencao.AUDITORIA_5A, Dono.PRODUTO)
INT_IA = Campo(Classe.INTERNA, BaseLegal.NAO_SE_APLICA, Retencao.AUDITORIA_5A, Dono.IA)
PSEUDO_CONTRATO = Campo(Classe.PSEUDONIMIZADA, BaseLegal.CONTRATO, Retencao.CONTATO_12M, Dono.DADOS)
PSEUDO_AUDITORIA = Campo(Classe.PSEUDONIMIZADA, BaseLegal.EXERCICIO_DE_DIREITOS, Retencao.AUDITORIA_5A, Dono.SEGURANCA)
TEXTO = Campo(Classe.TEXTO_LIVRE, BaseLegal.CONTRATO, Retencao.OPERACIONAL_90D, Dono.SEGURANCA)


def _todos(campo: Campo, colunas: str) -> dict[str, Campo]:
    return {c: campo for c in colunas.split()}


CATALOGO: dict[str, dict[str, Campo]] = {
    "data/reference/setores_rmsp.csv": _todos(PUB, "cd_setor cd_mun municipio distrito situacao ipvs_grupo ipvs_nome "
                                                   "lat lon subprefeitura regiao"),
    "data/reference/regioes.csv": _todos(PUB, "regiao municipio setores_classificados setores_vulneraveis ipvs_medio "
                                              "lat lon pct_vulneravel indice_vulnerabilidade"),
    "data/processed/contexto_diario.csv": _todos(INT_OPER, "data dia_semana mes feriado chuva"),
    "data/processed/doadores.csv": {
        **_todos(PSEUDO_CONTRATO, "doador_id documento_hash lat lon cd_setor"),
        **_todos(INT_OPER, "regiao municipio ipvs_grupo tipo_doador segmento tem_refrigeracao pode_entregar"),
    },
    "data/processed/ongs.csv": {
        **_todos(PSEUDO_CONTRATO, "ong_id documento_hash"),
        **_todos(INT_OPER, "cd_setor regiao municipio ipvs_grupo lat lon status_aprovacao capacidade_kg_dia "
                           "tem_refrigeracao serve_refeicao turnos tem_cozinha distribui_cestas tem_freezer "
                           "pode_buscar abertura_h fechamento_h categorias_aceitas"),
    },
    "data/processed/hubs.csv": _todos(INT_OPER, "hub_id cd_setor regiao municipio ipvs_grupo lat lon tipo validado_admin"),
    "data/processed/transportadores.csv": {
        **_todos(PSEUDO_CONTRATO, "transportador_id lat lon"),
        **_todos(INT_OPER, "modalidade veiculo refrigerado capacidade_kg regiao municipio rota_b_regiao "
                           "rota_b_lat rota_b_lon"),
    },
    "data/processed/pedidos.csv": {
        **_todos(PSEUDO_AUDITORIA, "ong_id"),
        **_todos(INT_OPER, "pedido_id categoria kg ts_abertura ts_expira kg_atendido status"),
    },
    "data/processed/lotes.csv": {
        "descricao_texto": TEXTO,
        **_todos(PSEUDO_AUDITORIA, "doador_id ong_id transportador_id"),
        **_todos(INT_IA, "texto_adversarial tipo_adversarial prioridade_regra prioridade hora dia_semana mes "
                         "fim_de_semana feriado n_ongs_compativeis_10km dist_ong_top_km min_ate_receber_top "
                         "doador_pode_entregar n_transportadores_ativos_raio refrigerado_disponivel "
                         "doador_tem_refrigeracao"),
        **_todos(INT_OPER, "lote_id tipo_doador segmento regiao ts_cadastro categoria armazenamento peso_kg ts_preparo "
                           "validade_rotulo ts_saida_refrigeracao validade_informada validade_efetiva horas_restantes "
                           "rota_expressa requer_preparo alergenicos bloqueio_questionario n_ofertas_ong "
                           "escalado_admin rodadas_ong rodadas_transporte orientado_refrigerar "
                           "refrigerado_apos_orientacao ts_aceite_ong minutos_ate_match complementaridade "
                           "ong_tinha_pedido modalidade hub_id acionou_pago ts_coleta minutos_trajeto "
                           "minutos_espera_janela pedido_atendido status_final descartado motivo_descarte ts_entrega "
                           "refeicoes prioridade_operacional custo_caixa aprovacao_caixa caixa_aprovado"),
    },
    "data/processed/eventos.csv.gz": {
        "ator": PSEUDO_AUDITORIA,
        **_todos(INT_OPER, "evento_id lote_id ts tipo detalhe"),
    },
}


def campos_por_classe() -> dict[str, int]:
    contagem: dict[str, int] = {}
    for colunas in CATALOGO.values():
        for campo in colunas.values():
            contagem[campo.classe] = contagem.get(campo.classe, 0) + 1
    return contagem
