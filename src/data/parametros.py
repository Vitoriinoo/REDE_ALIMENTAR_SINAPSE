"""Premissas numéricas da simulação (regras, seção 8.1).

Todas as suposições do gerador ficam AQUI, separadas da lógica, para que o grupo
possa revisar e calibrar sem mexer no código de simulação. As regras de negócio
(prazos, tetos, faixas) NÃO ficam aqui: vêm de `src.regras`.
"""

from datetime import date

from src.regras.dominio import Categoria as C

SEED = 42
INICIO = date(2025, 9, 1)
FIM = date(2026, 8, 31)  # 12 meses de cadastros
DIAS_FOLGA = 120  # o calendário da simulação continua após FIM para as rodadas pendentes

# --- Entidades ---------------------------------------------------------------------
N_DOADORES_PF = 90
DOADORES_PJ_POR_SEGMENTO = {"restaurante": 75, "mercado": 40, "padaria": 40, "hortifruti": 25, "industria": 30}
N_ONGS = 60
ONGS_PENDENTES = 3  # aguardando aprovação do Admin: não entram no matching
ONGS_REPROVADAS = 2  # tentativa de cadastro com CNPJ inválido / fachada
N_HUBS = 40
N_VOLUNTARIOS = 70
N_MOTORISTAS_RETORNO = 65
N_TRANSPORTADORAS = 25

# Peso de sorteio do setor censitário por grupo IPVS (1 = baixíssima ... 6 = muito alta).
# Doador PJ tende a ficar em área comercial/rica; ONG, em área vulnerável (descompasso).
PESO_SETOR_DOADOR_PJ = {1: 5.0, 2: 4.0, 3: 2.0, 4: 1.2, 5: 0.6, 6: 0.4}
PESO_SETOR_DOADOR_PF = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0}
PESO_SETOR_ONG = {1: 0.2, 2: 0.4, 3: 0.8, 4: 1.5, 5: 3.0, 6: 3.5}
PESO_SETOR_HUB = {1: 1.0, 2: 1.0, 3: 1.2, 4: 1.5, 5: 2.0, 6: 2.0}

# --- Frequência e mix de doações por segmento ----------------------------------------
DOACOES_POR_SEMANA = {
    "restaurante": 2.0, "mercado": 2.6, "padaria": 3.0, "hortifruti": 2.5, "industria": 0.8, "pf": 0.15,
}
MIX_CATEGORIAS = {
    "restaurante": {C.PREPARADO: 0.70, C.REFRIGERADO: 0.10, C.CONGELADO: 0.05, C.HORTIFRUTI: 0.10, C.NAO_PERECIVEL: 0.05},
    "mercado": {C.REFRIGERADO: 0.25, C.CONGELADO: 0.10, C.HORTIFRUTI: 0.25, C.PADARIA: 0.10, C.NAO_PERECIVEL: 0.30},
    "padaria": {C.PADARIA: 0.75, C.PREPARADO: 0.15, C.REFRIGERADO: 0.10},
    "hortifruti": {C.HORTIFRUTI: 0.95, C.NAO_PERECIVEL: 0.05},
    "industria": {C.NAO_PERECIVEL: 0.60, C.REFRIGERADO: 0.20, C.CONGELADO: 0.20},
    "pf": {C.NAO_PERECIVEL: 1.00},  # v2.0: CPF só doa não perecível lacrado (regras 4.1)
}

# Peso do lote (kg): lognormal com mediana e dispersão (sigma do log).
PESO_MEDIANA_KG = {
    C.PREPARADO: 8.0, C.REFRIGERADO: 10.0, C.CONGELADO: 15.0,
    C.HORTIFRUTI: 20.0, C.PADARIA: 6.0, C.NAO_PERECIVEL: 25.0,
}
PESO_SIGMA = 0.7
PESO_MULTIPLICADOR_SEGMENTO = {"industria": 3.0, "mercado": 1.3, "pf": 0.2}
PESO_MIN_KG, PESO_MAX_KG = 0.5, 400.0

# --- Horários (tendência, não janela fixa: ~75% perto dos picos) ---------------------
# (hora do pico, desvio-padrão em horas, peso relativo); FUNCIONAMENTO = faixa do ruído uniforme.
PICOS_HORARIO = {
    "restaurante": [(15.0, 0.8, 0.55), (22.5, 0.6, 0.45)],
    "mercado": [(8.5, 0.8, 0.55), (18.0, 1.0, 0.45)],
    "padaria": [(19.0, 0.8, 1.0)],
    "hortifruti": [(9.0, 1.0, 0.5), (17.0, 1.0, 0.5)],
    "industria": [(10.0, 1.5, 0.5), (15.0, 1.5, 0.5)],
    "pf": [(20.0, 1.5, 1.0)],
}
FRACAO_NOS_PICOS = 0.75
FUNCIONAMENTO = {
    "restaurante": (11, 23.5), "mercado": (7, 22), "padaria": (6, 21),
    "hortifruti": (6, 19), "industria": (8, 18), "pf": (8, 22),
}

# --- Sazonalidade --------------------------------------------------------------------
# Multiplicador por dia da semana (0 = segunda ... 6 = domingo).
MULT_DIA_SEMANA = {
    "restaurante": [0.9, 0.9, 1.0, 1.0, 1.2, 1.3, 1.4],
    "mercado": [1.0, 1.0, 1.0, 1.0, 1.1, 1.2, 0.8],
    "padaria": [1.0, 1.0, 1.0, 1.0, 1.0, 1.2, 1.1],
    "hortifruti": [1.0, 1.0, 1.0, 1.0, 1.1, 1.3, 0.6],
    "industria": [1.2, 1.2, 1.2, 1.2, 1.2, 0.1, 0.0],
    "pf": [0.6, 0.6, 0.6, 0.7, 0.8, 1.8, 1.9],
}
MULT_MES = {12: 1.30, 1: 0.90}  # festas de fim de ano / férias
MULT_FERIADO = 0.7
FERIADOS = [  # nacionais no período
    "2025-09-07", "2025-10-12", "2025-11-02", "2025-11-15", "2025-11-20", "2025-12-25",
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-04-03", "2026-04-21", "2026-05-01", "2026-06-04",
]

# --- Clima (fator LATENTE: o Modelo 2 não vê) ---------------------------------------
# Probabilidade de dia chuvoso por mês (verão chuvoso em SP).
PROB_CHUVA_MES = {1: 0.60, 2: 0.55, 3: 0.50, 4: 0.30, 5: 0.25, 6: 0.15,
                  7: 0.12, 8: 0.12, 9: 0.25, 10: 0.35, 11: 0.45, 12: 0.55}
CHUVA_MULT_DISPONIBILIDADE = 0.65  # voluntários e motos saem menos
CHUVA_MULT_VELOCIDADE = 0.80

# --- Validade no momento do cadastro -------------------------------------------------
PROB_AMBIENTE = {C.PREPARADO: 0.55, C.REFRIGERADO: 0.08, C.CONGELADO: 0.05}
PREPARO_AMBIENTE_HORAS_ATRAS = (0.15, 1.7)  # uniforme: há quanto tempo foi preparado
PREPARO_REFRIGERADO_HORAS_ATRAS = (1.0, 66.0)
SAIDA_REFRIGERACAO_HORAS_ATRAS = (0.1, 1.8)
# Validade restante (rótulo/informada) em dias: lognormal (mediana, sigma).
VALIDADE_RESTANTE_DIAS = {
    C.REFRIGERADO: (2.5, 0.7), C.CONGELADO: (6.0, 0.8),
    C.HORTIFRUTI: (2.5, 0.5), C.PADARIA: (1.4, 0.6), C.NAO_PERECIVEL: (25.0, 0.7),
}

# Rótulo de prioridade: fração alterada em ±1 nível (discordância de triadores).
RUIDO_ROTULO_PRIORIDADE = 0.09

# --- ONGs ----------------------------------------------------------------------------
ONG_CAPACIDADE_MEDIANA_KG = 60.0  # ONGs pequenas lotam: capacidade vira gargalo em picos
ONG_CAPACIDADE_SIGMA = 0.6
ONG_PROB_REFRIGERACAO = 0.60
ONG_PROB_SERVE_REFEICAO = 0.70  # cozinhas comunitárias; as demais distribuem cestas
# "noturno" = distribuição à noite (ex.: coletivos que atendem a população em situação de rua).
ONG_TURNOS = {"cafe": (7, 8), "almoco": (11.5, 13.5), "jantar": (18, 19.5), "noturno": (20, 23)}
ONG_PROB_TURNO = {"cafe": 0.35, "almoco": 0.90, "jantar": 0.55, "noturno": 0.20}
# v2.0: capacidades declaradas (regras 6.4). Quem serve refeição quase sempre tem cozinha;
# quem não serve distribui cestas (a família cozinha em casa).
ONG_PROB_COZINHA = {True: 0.85, False: 0.15}  # chave = serve_refeicao
ONG_PROB_CESTAS = {True: 0.30, False: 1.00}
ONG_PROB_FREEZER_SE_REFRIGERACAO = 0.60
ONG_PROB_VEICULO = 0.35  # pode buscar o lote no doador (regras 6.6)
ONG_PROB_RECUSAR_CATEGORIA = 0.10  # preferência: a ONG tira da lista algo que a estrutura comportaria
# Janela de recebimento (abertura, fechamento) e peso; ONG com turno noturno recebe até 23 h.
ONG_JANELAS = [((7, 21), 0.40), ((8, 18), 0.35), ((9, 17), 0.15), ((13, 22), 0.10)]
ONG_FECHAMENTO_NOTURNO = 23
ONG_PROB_ACEITE_BASE = 0.78
ONG_PROB_ACEITE_FORA_HORARIO = 0.25
ONG_RESPOSTA_MEDIA_FRACAO_PRAZO = 0.45  # tempo de resposta ~ exponencial com média = fração do prazo
ADMIN_ATRASO_MIN = (20, 90)
ADMIN_PROB_REALOCAR = 0.5

# Orientação de refrigeração na rota expressa (7.5): doador com geladeira segue a
# orientação com esta probabilidade; doador sem geladeira não consegue.
PROB_DOADOR_REFRIGERA = 0.70
TEMPO_ATE_REFRIGERAR_MIN = (5, 30)

# --- Transporte ----------------------------------------------------------------------
FATOR_CIRCUITO = 1.35  # distância em linha reta -> distância viária
VELOCIDADE_KMH = {"moto": 28.0, "carro": 24.0, "van": 22.0, "caminhao": 18.0}
PICOS_TRANSITO = [(7, 10), (17, 20)]
TRANSITO_MULT_VELOCIDADE = 0.65
VARIACAO_TRAJETO_SIGMA = 0.25  # imprevisto real vs. estimado (latente)

VOLUNTARIO_PROB_ATIVO_DIA = 0.25
MOTORISTA_PROB_ATIVO_DIA = 0.30
TRANSPORTADORA_PROB_ATIVA_UTIL = 0.55
TRANSPORTADORA_PROB_ATIVA_FDS = 0.10
TRANSPORTADORA_PROB_REFRIGERADA = 0.40
MOTORISTA_PROB_REFRIGERADO = 0.10
RAIO_TRANSPORTADOR_KM = 12.0
DESVIO_MAX_ROTA_KM = 4.0  # transportadora aceita se o doador está até X km da rota A->B
PROB_ACEITE_GRATUITO = 0.35
TEMPO_ACEITE_GRATUITO_MEDIO_MIN = 22.0
# v2.0: buscar/entregar depende do que doador e ONG DECLARARAM (regras 6.6); estas são as
# chances de o veículo declarado estar disponível no momento.
PROB_ONG_RETIRA_DISPONIVEL = 0.70
PROB_DOADOR_ENTREGA_DISPONIVEL = 0.60
DOADOR_PROB_PODE_ENTREGAR = {
    "restaurante": 0.25, "mercado": 0.35, "padaria": 0.20, "hortifruti": 0.40, "industria": 0.50, "pf": 0.60,
}
DOADOR_ENTREGA_DIST_MAX_KM = 6.0
CHEGADA_ATE_DOADOR_MIN = (8, 35)
ATRASO_HUB_MIN = (20, 60)

APP_PROB_DISPONIVEL = 0.92
APP_PROB_DISPONIVEL_CHUVA = 0.70
APP_TARIFA_BASE = 8.0
APP_TARIFA_POR_KM = 2.2
APP_CHEGADA_MIN = (8, 22)
ONG_CONFIRMA_CAIXA_MIN = (2, 10)
GESTOR_APROVA_MIN = (10, 60)
GESTOR_PROB_APROVA = 0.85

# Margem de consumo: o lote precisa chegar antes de (validade efetiva - margem).
MARGEM_CONSUMO_HORAS = {
    C.PREPARADO: 0.5, C.REFRIGERADO: 12.0, C.CONGELADO: 24.0,
    C.HORTIFRUTI: 12.0, C.PADARIA: 6.0, C.NAO_PERECIVEL: 72.0,
}
PROB_DESCARTE_QUEBRA_CADEIA_FRIA = 0.6  # quando o trajeto real estoura o limite

# Inspeção na entrega: a ONG pode recusar o lote na porta. Probabilidade =
# (base + fator x fração_da_vida_útil_consumida²) x qualidade_latente (lognormal, o modelo não vê).
INSPECAO_BASE = {
    C.PREPARADO: 0.02, C.REFRIGERADO: 0.01, C.CONGELADO: 0.005,
    C.HORTIFRUTI: 0.03, C.PADARIA: 0.015, C.NAO_PERECIVEL: 0.002,
}
INSPECAO_FATOR = {
    C.PREPARADO: 0.20, C.REFRIGERADO: 0.25, C.CONGELADO: 0.10,
    C.HORTIFRUTI: 0.45, C.PADARIA: 0.30, C.NAO_PERECIVEL: 0.02,
}
INSPECAO_SIGMA_QUALIDADE = 0.4

# Heurística operacional pré-IA usada no histórico para acionar o transporte pago
# (o Modelo 2 substitui essa heurística em produção): risco alto se faltam menos de
# X horas para o limite de consumo.
HEURISTICA_RISCO_HORAS = 4.0

# Rodadas: se ninguém aceita (ONG ou transporte), o sistema tenta de novo depois do
# intervalo, dentro do horário de operação, até o limite de consumo do lote.
INTERVALO_RODADA_HORAS = 4.0
HORARIO_OPERACAO = (7, 21)
JANELA_RODADA_TRANSPORTE_MIN = 180
MAX_RODADAS = 30

# --- Questionário do lote (regras 4.5) -------------------------------------------------
# Chance de o lote precisar de preparo antes do consumo (Q4): arroz cru sim, enlatado não.
PROB_REQUER_PREPARO = {
    C.PREPARADO: 0.0, C.PADARIA: 0.0, C.REFRIGERADO: 0.30, C.CONGELADO: 0.80, C.HORTIFRUTI: 0.50, C.NAO_PERECIVEL: 0.60,
}
# Respostas que bloqueiam (o doador declara a verdade na simulação).
PROB_EMBALAGEM_VIOLADA = 0.010
PROB_EXPOSTO_CONSUMIDOR = 0.030  # Preparado
PROB_ROTULO_AUSENTE = 0.010  # Refrigerado, Congelado
PROB_DESCONGELADO = 0.020  # Congelado
PROB_PF_SEM_LACRE = 0.040
PROB_HORTIFRUTI_NAO_SELECIONADO = 0.020
# Alergênicos mais comuns por categoria (informativo, segue para a ONG).
ALERGENICOS_PROVAVEIS = {
    C.PREPARADO: ["gluten", "leite", "ovos", "soja"], C.REFRIGERADO: ["leite"], C.CONGELADO: ["peixes", "crustaceos"],
    C.HORTIFRUTI: [], C.PADARIA: ["gluten", "leite", "ovos"], C.NAO_PERECIVEL: ["gluten", "soja", "amendoim"],
}
PROB_CADA_ALERGENICO = 0.35

# --- Pedidos das ONGs (regras 6.5) -----------------------------------------------------
PEDIDOS_POR_SEMANA_POR_ONG = 0.5
PEDIDO_PESO_CATEGORIA = {
    C.NAO_PERECIVEL: 0.40, C.HORTIFRUTI: 0.25, C.PREPARADO: 0.10, C.PADARIA: 0.10, C.REFRIGERADO: 0.10, C.CONGELADO: 0.05,
}
PEDIDO_FRACAO_CAPACIDADE = (0.3, 1.0)
PEDIDO_VALIDADE_DIAS = (3, 7)

# --- Textos --------------------------------------------------------------------------
FRACAO_TEXTO_ADVERSARIAL = 0.015
