"""Simulação do processo de cada lote: cadastro -> triagem -> matching -> transporte -> desfecho.

O rótulo de descarte do Modelo 2 EMERGE deste processo (não é uma fórmula): depende
de aceites, tempos, frota e de fatores latentes que o modelo não vê (chuva, imprevisto
no trajeto). As regras de negócio vêm de `src.regras`, as mesmas que a API vai usar.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from src.data import parametros as P
from src.data.textos import descricao, descricao_adversarial
from src.regras.dominio import ORDEM_PRIORIDADE, Armazenamento, Categoria, Modalidade, Prioridade, TipoDoador
from src.regras.logistica import (
    ESPERA_TRANSPORTE_GRATUITO,
    MAX_RECUSAS_ANTES_DE_ESCALAR,
    PRAZO_ACEITE_ONG,
    RAIO_MAXIMO_KM,
    Aprovacao,
    PerfilOng,
    aprovacao_necessaria,
    complementaridade,
    motivo_incompatibilidade,
    pode_acionar_pago,
    pode_doar,
    proxima_abertura,
    score_ong,
    tempo_ate_receber,
    trajeto_maximo,
    transporte_elegivel,
)
from src.regras.questionario import Alergenico, Origem, Respostas, avaliar
from src.regras.prioridade import prioridade_por_regra
from src.regras.refeicoes import refeicoes
from src.regras.validade import (
    LoteRecusado,
    em_rota_expressa,
    validade_apos_refrigeracao,
    validade_efetiva,
    validar_aceite,
)

RAIO_TERRA_KM = 6371.0
MIN = timedelta(minutes=1)


# --- Geometria -------------------------------------------------------------------------
def distancia_km(lat1, lon1, lat2, lon2):
    """Haversine (vetorizado) x fator de circuito viário."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * RAIO_TERRA_KM * np.arcsin(np.sqrt(a)) * P.FATOR_CIRCUITO


def distancia_ponto_segmento_km(lat, lon, a_lat, a_lon, b_lat, b_lon):
    """Distância (linha reta) de um ponto ao segmento A-B, em projeção local equiretangular."""
    kx = 111.32 * np.cos(np.radians(lat))
    ky = 110.57
    px, py = 0.0, 0.0
    ax, ay = (a_lon - lon) * kx, (a_lat - lat) * ky
    bx, by = (b_lon - lon) * kx, (b_lat - lat) * ky
    dx, dy = bx - ax, by - ay
    comp2 = dx * dx + dy * dy
    t = np.where(comp2 > 0, np.clip(((px - ax) * dx + (py - ay) * dy) / np.where(comp2 > 0, comp2, 1), 0, 1), 0)
    return np.hypot(ax + t * dx - px, ay + t * dy - py)


def _horas(ts: datetime) -> float:
    return ts.hour + ts.minute / 60


# --- Estado da simulação -----------------------------------------------------------------
@dataclass
class Simulador:
    rng: np.random.Generator
    doadores: pd.DataFrame
    ongs: pd.DataFrame
    hubs: pd.DataFrame
    transportadores: pd.DataFrame
    contexto_diario: pd.DataFrame
    pedidos: pd.DataFrame | None = None
    eventos: list[dict] = field(default_factory=list)
    ong_kg_dia: dict = field(default_factory=lambda: defaultdict(float))
    caixa_dia: dict = field(default_factory=lambda: defaultdict(float))

    def __post_init__(self):
        self.ongs_ok = self.ongs[self.ongs["status_aprovacao"] == "aprovada"].reset_index(drop=True)
        self.perfis = [
            PerfilOng(
                categorias_aceitas=frozenset(Categoria(c) for c in o.categorias_aceitas.split("|")),
                tem_refrigeracao=bool(o.tem_refrigeracao), tem_freezer=bool(o.tem_freezer),
                tem_cozinha=bool(o.tem_cozinha), distribui_cestas=bool(o.distribui_cestas),
                pode_buscar=bool(o.pode_buscar), abertura_h=float(o.abertura_h), fechamento_h=float(o.fechamento_h),
            )
            for o in self.ongs_ok.itertuples()
        ]
        self.ctx = self.contexto_diario.set_index("data")
        self.ativos = self._sortear_transportadores_ativos()
        # Pedidos abertos por (ONG, categoria): [abertura, expira, kg_restante, pedido_id] (regras 6.5).
        self._pedidos: dict[tuple[str, str], list[list]] = defaultdict(list)
        if self.pedidos is not None:
            for p in self.pedidos.sort_values("ts_abertura").itertuples():
                self._pedidos[(p.ong_id, p.categoria)].append([p.ts_abertura, p.ts_expira, float(p.kg), p.pedido_id])

    # ---------- pedidos das ONGs ----------
    def _pedido_aberto(self, ong_id: str, categoria: Categoria, ts: datetime) -> list | None:
        for p in self._pedidos.get((ong_id, str(categoria)), ()):
            if p[0] <= ts < p[1] and p[2] > 0:
                return p
        return None

    def _atender_pedido(self, ong_id: str, categoria: Categoria, ts: datetime, kg: float) -> str | None:
        p = self._pedido_aberto(ong_id, categoria, ts)
        if p is None:
            return None
        p[2] = max(0.0, p[2] - kg)
        return p[3]

    def kg_restante_por_pedido(self) -> dict[str, float]:
        return {p[3]: p[2] for lista in self._pedidos.values() for p in lista}

    # ---------- preparação ----------
    def _sortear_transportadores_ativos(self) -> dict[date, np.ndarray]:
        t = self.transportadores
        ativos = {}
        for dia, linha in self.ctx.iterrows():
            fds = linha["dia_semana"] >= 5
            p = np.where(
                t["modalidade"] == "voluntario", P.VOLUNTARIO_PROB_ATIVO_DIA,
                np.where(t["modalidade"] == "motorista_retorno", P.MOTORISTA_PROB_ATIVO_DIA,
                         P.TRANSPORTADORA_PROB_ATIVA_FDS if fds else P.TRANSPORTADORA_PROB_ATIVA_UTIL),
            )
            if linha["chuva"]:
                p = np.where(t["modalidade"] == "transportadora", p, p * P.CHUVA_MULT_DISPONIBILIDADE)
            ativos[dia] = np.flatnonzero(self.rng.random(len(t)) < p)
        return ativos

    def _evento(self, lote_id: str, ts: datetime, tipo: str, ator: str, detalhe: str = "") -> None:
        self.eventos.append({"lote_id": lote_id, "ts": ts, "tipo": tipo, "ator": ator, "detalhe": detalhe})

    def _velocidade(self, veiculo: str, ts: datetime, chuva: bool, estimada: bool) -> float:
        v = P.VELOCIDADE_KMH[veiculo]
        if any(ini <= _horas(ts) < fim for ini, fim in P.PICOS_TRANSITO):
            v *= P.TRANSITO_MULT_VELOCIDADE
        if chuva and not estimada:  # a estimativa do sistema não conhece a chuva (latente)
            v *= P.CHUVA_MULT_VELOCIDADE
        return v

    def _minutos_trajeto(self, km: float, veiculo: str, ts: datetime, chuva: bool, estimada: bool) -> float:
        minutos = km / self._velocidade(veiculo, ts, chuva, estimada) * 60
        if not estimada:
            minutos *= self.rng.lognormal(0, P.VARIACAO_TRAJETO_SIGMA)
        return minutos

    # ---------- cadastro ----------
    def _cadastro(self, doador, categoria: Categoria, ts: datetime) -> dict:
        rng = self.rng
        prob_amb = P.PROB_AMBIENTE.get(categoria)
        if categoria == Categoria.CONGELADO:
            armazenamento = Armazenamento.AMBIENTE if rng.random() < prob_amb else Armazenamento.CONGELADO
        elif prob_amb is not None:
            armazenamento = Armazenamento.AMBIENTE if rng.random() < prob_amb else Armazenamento.REFRIGERADO
        else:
            armazenamento = Armazenamento.AMBIENTE

        mult = P.PESO_MULTIPLICADOR_SEGMENTO.get(doador.segmento, 1.0)
        peso = float(np.clip(rng.lognormal(np.log(P.PESO_MEDIANA_KG[categoria] * mult), P.PESO_SIGMA),
                             P.PESO_MIN_KG, P.PESO_MAX_KG))

        info = {"ts_preparo": None, "validade_rotulo": None, "ts_saida_refrigeracao": None, "validade_informada": None}
        if categoria == Categoria.PREPARADO:
            faixa = P.PREPARO_AMBIENTE_HORAS_ATRAS if armazenamento == Armazenamento.AMBIENTE else P.PREPARO_REFRIGERADO_HORAS_ATRAS
            info["ts_preparo"] = ts - timedelta(hours=rng.uniform(*faixa))
        else:
            mediana, sigma = P.VALIDADE_RESTANTE_DIAS[categoria]
            vence = ts + timedelta(days=float(rng.lognormal(np.log(mediana), sigma)))
            if categoria in (Categoria.REFRIGERADO, Categoria.CONGELADO):
                info["validade_rotulo"] = vence
                if armazenamento == Armazenamento.AMBIENTE:
                    info["ts_saida_refrigeracao"] = ts - timedelta(hours=rng.uniform(*P.SAIDA_REFRIGERACAO_HORAS_ATRAS))
            else:
                info["validade_informada"] = vence

        validade = validade_efetiva(
            categoria, armazenamento, preparo=info["ts_preparo"], validade_rotulo=info["validade_rotulo"],
            saida_refrigeracao=info["ts_saida_refrigeracao"], validade_informada=info["validade_informada"],
        )

        if rng.random() < P.FRACAO_TEXTO_ADVERSARIAL:
            texto, tipo_adv = descricao_adversarial(rng)
        else:
            texto, tipo_adv = descricao(rng, categoria, armazenamento, peso), None

        respostas = self._questionario(doador, categoria)
        motivos_q = avaliar(categoria, TipoDoador(doador.tipo_doador), respostas)

        return {
            "categoria": str(categoria), "armazenamento": str(armazenamento), "peso_kg": round(peso, 1),
            "descricao_texto": texto, "texto_adversarial": tipo_adv is not None, "tipo_adversarial": tipo_adv,
            **info, "validade_efetiva": validade, "horas_restantes": round((validade - ts) / timedelta(hours=1), 2),
            "rota_expressa": em_rota_expressa(categoria, armazenamento),
            "requer_preparo": respostas.requer_preparo,
            "alergenicos": "|".join(sorted(a.value for a in respostas.alergenicos)),
            "bloqueio_questionario": "|".join(motivos_q) or None,
        }

    def _questionario(self, doador, categoria: Categoria) -> Respostas:
        """Respostas do doador (regras 4.5). Na simulação o doador declara a verdade."""
        rng = self.rng
        provaveis = [a for a in P.ALERGENICOS_PROVAVEIS[categoria] if rng.random() < P.PROB_CADA_ALERGENICO]
        alergenicos = frozenset(Alergenico(a) for a in provaveis) or frozenset({Alergenico.NENHUM})
        pf = doador.tipo_doador == "PF"
        refrig_ou_cong = categoria in (Categoria.REFRIGERADO, Categoria.CONGELADO)
        return Respostas(
            origem=Origem.EXCEDENTE_ESTOQUE if categoria == Categoria.NAO_PERECIVEL else Origem.EXCEDENTE_PRODUCAO,
            embalagem_integra=bool(rng.random() >= P.PROB_EMBALAGEM_VIOLADA),
            alergenicos=alergenicos,
            requer_preparo=bool(rng.random() < P.PROB_REQUER_PREPARO[categoria]),
            declaracao_condicoes=True,
            exposto_consumidor=bool(rng.random() < P.PROB_EXPOSTO_CONSUMIDOR) if categoria == Categoria.PREPARADO else None,
            rotulo_visivel=bool(rng.random() >= P.PROB_ROTULO_AUSENTE) if refrig_ou_cong else None,
            descongelado=bool(rng.random() < P.PROB_DESCONGELADO) if categoria == Categoria.CONGELADO else None,
            lacrado_original=bool(rng.random() >= P.PROB_PF_SEM_LACRE) if pf else None,
            selecionado=bool(rng.random() >= P.PROB_HORTIFRUTI_NAO_SELECIONADO)
            if categoria == Categoria.HORTIFRUTI else None,
        )

    def _rotulo_prioridade(self, regra: Prioridade, expressa: bool) -> Prioridade:
        # Discordância de triadores humanos (±1 nível). A rota expressa é inequívoca: sem ruído.
        if expressa or self.rng.random() >= P.RUIDO_ROTULO_PRIORIDADE:
            return regra
        i = ORDEM_PRIORIDADE.index(regra)
        passo = self.rng.choice([-1, 1]) if 0 < i < len(ORDEM_PRIORIDADE) - 1 else (1 if i == 0 else -1)
        return ORDEM_PRIORIDADE[i + passo]

    # ---------- ONGs ----------
    def _turno_a_tempo(self, turnos: str, agora: datetime, limite: datetime) -> bool:
        """A ONG serve alguma refeição começando (ou em andamento) antes do limite de consumo?"""
        if not turnos:
            return False
        for offset in (0, 1):
            dia = agora.date() + timedelta(days=offset)
            for turno in turnos.split("|"):
                ini, fim = P.ONG_TURNOS[turno]
                t_ini = datetime.combine(dia, datetime.min.time()) + timedelta(hours=ini)
                t_fim = datetime.combine(dia, datetime.min.time()) + timedelta(hours=fim)
                if t_fim > agora and max(t_ini, agora) <= limite:
                    return True
        return False

    def _ranking_ongs(self, doador, cad: dict, categoria: Categoria, armazenamento: Armazenamento, ts: datetime):
        """Filtros obrigatórios (regras 6.1, etapa 1) e score v2 (etapa 2).

        Cada candidato: dict com score, índice da ONG, distância, kg já usados no dia,
        minutos até poder receber, complementaridade e se havia pedido aberto.
        """
        o = self.ongs_ok
        dist = distancia_km(doador.lat, doador.lon, o["lat"].to_numpy(), o["lon"].to_numpy())
        limite_consumo = cad["validade_efetiva"] - timedelta(hours=P.MARGEM_CONSUMO_HORAS[categoria])
        dia = ts.date()
        candidatos = []
        for i, ong in enumerate(o.itertuples()):
            perfil = self.perfis[i]
            if dist[i] > RAIO_MAXIMO_KM:
                continue
            if motivo_incompatibilidade(categoria, armazenamento, cad["requer_preparo"], perfil) is not None:
                continue
            usado = self.ong_kg_dia[(ong.ong_id, dia)]
            if usado + cad["peso_kg"] > ong.capacidade_kg_dia:
                continue
            a_tempo = self._turno_a_tempo(ong.turnos, ts, limite_consumo)
            trajeto = timedelta(minutes=self._minutos_trajeto(dist[i], "carro", ts, False, estimada=True))
            ate_receber = tempo_ate_receber(ts, trajeto, perfil.abertura_h, perfil.fechamento_h)
            if ts + ate_receber > limite_consumo:  # disponibilidade: não consegue receber a tempo
                continue
            if cad["rota_expressa"]:
                trajeto_moto = timedelta(minutes=self._minutos_trajeto(dist[i], "moto", ts, False, estimada=True))
                if not a_tempo or not transporte_elegivel(categoria, armazenamento, False, trajeto_moto):
                    continue
            livre = 1 - usado / ong.capacidade_kg_dia
            comp = complementaridade(bool(doador.pode_entregar), perfil.pode_buscar)
            pedido = self._pedido_aberto(ong.ong_id, categoria, ts) is not None
            candidatos.append({
                "score": score_ong(ate_receber, livre, int(ong.ipvs_grupo), a_tempo, comp, pedido), "i": i,
                "km": float(dist[i]), "usado": usado, "min_receber": ate_receber / MIN,
                "complementaridade": str(comp), "pedido": pedido,
            })
        candidatos.sort(key=lambda c: c["score"], reverse=True)
        return candidatos

    def _oferecer_ongs(self, lote_id: str, ranking, prioridade: Prioridade, ts: datetime):
        """Oferta sequencial com prazo; após 3 falhas, escala para o Admin. Devolve (idx, t_aceite, n_ofertas, escalou)."""
        rng, o = self.rng, self.ongs_ok
        prazo = PRAZO_ACEITE_ONG[prioridade]
        t = ts
        for n, cand in enumerate(ranking[:MAX_RECUSAS_ANTES_DE_ESCALAR], start=1):
            i, usado = cand["i"], cand["usado"]
            ong = o.iloc[i]
            ator = f"ong:{ong.ong_id}"
            self._evento(lote_id, t, "OFERTA_ONG", ator, f"prazo={int(prazo / MIN)}min")
            fora = not (ong.abertura_h <= _horas(t) < ong.fechamento_h)
            p = P.ONG_PROB_ACEITE_FORA_HORARIO if fora else P.ONG_PROB_ACEITE_BASE
            p *= 1 - 0.8 * (usado / ong.capacidade_kg_dia) ** 2
            resposta = timedelta(minutes=float(rng.exponential(P.ONG_RESPOSTA_MEDIA_FRACAO_PRAZO * prazo / MIN)))
            if resposta > prazo:
                t += prazo
                self._evento(lote_id, t, "EXPIRACAO_ONG", ator)
            elif rng.random() < p:
                t += resposta
                self._evento(lote_id, t, "ACEITE_ONG", ator)
                return i, t, n, False
            else:
                t += resposta
                self._evento(lote_id, t, "RECUSA_ONG", ator)

        n_ofertas = min(len(ranking), MAX_RECUSAS_ANTES_DE_ESCALAR)
        if len(ranking) <= MAX_RECUSAS_ANTES_DE_ESCALAR:
            return None, t, n_ofertas, False
        self._evento(lote_id, t, "ESCALADA_ADMIN", "admin", f"{n_ofertas} recusas/expirações")
        t += timedelta(minutes=float(rng.uniform(*P.ADMIN_ATRASO_MIN)))
        if rng.random() < P.ADMIN_PROB_REALOCAR:
            i = ranking[MAX_RECUSAS_ANTES_DE_ESCALAR]["i"]
            self._evento(lote_id, t, "REALOCACAO_ADMIN", "admin", f"ong:{o.iloc[i].ong_id}")
            return i, t, n_ofertas + 1, True
        return None, t, n_ofertas, True

    # ---------- transporte ----------
    def _candidatos_gratuitos(self, doador, ong, km: float, categoria, armazenamento, peso: float, ts: datetime, chuva: bool):
        """Lista (modalidade, veiculo, refrigerado, transportador_id, prob_aceite, tempo_medio_min)."""
        cand = []
        tipo = TipoDoador(doador.tipo_doador)
        # v2.0: só entrega/busca quem DECLAROU ter transporte (regras 6.6).
        if doador.pode_entregar and (km <= P.DOADOR_ENTREGA_DIST_MAX_KM or tipo == TipoDoador.PF):
            cand.append((Modalidade.DOADOR_ENTREGA, "carro", False, None, P.PROB_DOADOR_ENTREGA_DISPONIVEL, 10.0))
        if ong.pode_buscar:
            cand.append((Modalidade.ONG_RETIRA, "carro", False, None, P.PROB_ONG_RETIRA_DISPONIVEL, 12.0))

        t = self.transportadores.iloc[self.ativos[ts.date()]]
        if len(t):
            d_base = distancia_km(doador.lat, doador.lon, t["lat"].to_numpy(), t["lon"].to_numpy())
            e_tra = (t["modalidade"] == "transportadora").to_numpy()
            perto = np.zeros(len(t), dtype=bool)
            perto[~e_tra] = d_base[~e_tra] <= P.RAIO_TRANSPORTADOR_KM
            if e_tra.any():
                tr = t[e_tra]
                args = (tr["lat"].to_numpy(), tr["lon"].to_numpy(), tr["rota_b_lat"].to_numpy(), tr["rota_b_lon"].to_numpy())
                d_doador = distancia_ponto_segmento_km(doador.lat, doador.lon, *args)
                d_ong = distancia_ponto_segmento_km(ong.lat, ong.lon, *args)
                perto[e_tra] = (d_doador <= P.DESVIO_MAX_ROTA_KM) & (d_ong <= P.DESVIO_MAX_ROTA_KM)
            for tr in t[perto & (t["capacidade_kg"].to_numpy() >= peso)].itertuples():
                p = P.PROB_ACEITE_GRATUITO
                if chuva and tr.modalidade != "transportadora":
                    p *= P.CHUVA_MULT_DISPONIBILIDADE
                cand.append((Modalidade(tr.modalidade), tr.veiculo, bool(tr.refrigerado), tr.transportador_id,
                             p, P.TEMPO_ACEITE_GRATUITO_MEDIO_MIN))

        elegiveis = []
        for c in cand:
            trajeto = timedelta(minutes=self._minutos_trajeto(km, c[1], ts, chuva, estimada=True))
            if transporte_elegivel(categoria, armazenamento, c[2], trajeto):
                elegiveis.append(c)
        return elegiveis

    def _hub_mais_proximo(self, doador) -> str:
        d = distancia_km(doador.lat, doador.lon, self.hubs["lat"].to_numpy(), self.hubs["lon"].to_numpy())
        return str(self.hubs.iloc[int(np.argmin(d))].hub_id)

    # ---------- processo completo ----------
    def _proxima_rodada(self, t: datetime) -> datetime:
        """Nova tentativa após o intervalo, sempre dentro do horário de operação."""
        prox = t + timedelta(hours=P.INTERVALO_RODADA_HORAS)
        ini, fim = P.HORARIO_OPERACAO
        if _horas(prox) >= fim or _horas(prox) < ini:
            dia = prox.date() + timedelta(days=1 if _horas(prox) >= fim else 0)
            prox = datetime.combine(dia, datetime.min.time()) + timedelta(hours=ini)
        return prox

    def _tentar_pago(self, lote_id, ong, km, categoria, armazenamento, prioridade, t_decisao, espera, limite, chuva, extra):
        """Aciona o entregador de app se a regra permitir. Devolve o horário de aceite ou None."""
        rng = self.rng
        estimado = self._minutos_trajeto(km, "moto", t_decisao, chuva, estimada=True)
        risco_alto = (limite - t_decisao) < timedelta(hours=P.HEURISTICA_RISCO_HORAS)
        if not (pode_acionar_pago(prioridade, espera, risco_alto)
                and transporte_elegivel(categoria, armazenamento, False, timedelta(minutes=estimado))):
            return None
        self._evento(lote_id, t_decisao, "ACIONA_PAGO", "sistema", "heuristica_risco_v0")
        custo = round(P.APP_TARIFA_BASE + P.APP_TARIFA_POR_KM * km, 2)
        chave = (ong.ong_id, t_decisao.date())
        aprovacao = aprovacao_necessaria(custo, self.caixa_dia[chave])
        if aprovacao == Aprovacao.CONFIRMACAO_ONG:
            t_aprov = t_decisao + timedelta(minutes=float(rng.uniform(*P.ONG_CONFIRMA_CAIXA_MIN)))
            aprovado, ator = True, f"ong:{ong.ong_id}"
        else:
            t_aprov = t_decisao + timedelta(minutes=float(rng.uniform(*P.GESTOR_APROVA_MIN)))
            aprovado, ator = bool(rng.random() < P.GESTOR_PROB_APROVA), "gestor_caixa"
        self._evento(lote_id, t_aprov, "APROVACAO_CAIXA" if aprovado else "CAIXA_NEGADO", ator, f"R${custo:.2f}")
        extra |= {"custo_caixa": custo, "aprovacao_caixa": str(aprovacao), "caixa_aprovado": aprovado}
        disponivel = rng.random() < (P.APP_PROB_DISPONIVEL_CHUVA if chuva else P.APP_PROB_DISPONIVEL)
        if not (aprovado and disponivel):
            return None
        self.caixa_dia[chave] += custo
        return t_aprov

    def _chuva(self, t: datetime) -> bool:
        return bool(self.ctx.loc[t.date()]["chuva"]) if t.date() in self.ctx.index else False

    def simular_lote(self, lote_id: str, doador, categoria: Categoria, ts: datetime) -> dict:
        rng = self.rng
        ctx = self.ctx.loc[ts.date()]
        base = {
            "lote_id": lote_id, "doador_id": doador.doador_id, "tipo_doador": doador.tipo_doador,
            "segmento": doador.segmento, "regiao": doador.regiao, "ts_cadastro": ts,
        }
        assert pode_doar(TipoDoador(doador.tipo_doador), categoria)
        cad = self._cadastro(doador, categoria, ts)
        armazenamento = Armazenamento(cad["armazenamento"])
        base |= cad
        self._evento(lote_id, ts, "CADASTRO", f"doador:{doador.doador_id}", categoria)

        if cad["bloqueio_questionario"]:
            self._evento(lote_id, ts, "BLOQUEIO_QUESTIONARIO", "sistema", cad["bloqueio_questionario"])
            return base | {"status_final": "BLOQUEADO", "motivo_descarte": "QUESTIONARIO"}
        try:
            restante = validar_aceite(categoria, armazenamento, cad["validade_efetiva"], ts)
        except LoteRecusado as e:
            self._evento(lote_id, ts, "BLOQUEIO_VALIDADE", "sistema", e.motivo[:80])
            return base | {"status_final": "BLOQUEADO", "motivo_descarte": "VALIDADE_ABAIXO_DO_MINIMO"}

        regra = prioridade_por_regra(categoria, armazenamento, restante, cad["peso_kg"])
        prioridade = self._rotulo_prioridade(regra, cad["rota_expressa"])
        self._evento(lote_id, ts, "TRIAGEM", "triador", str(prioridade))

        # Contexto no momento da decisão (features do Modelo 2: nada do desfecho entra aqui).
        estado = dict(cad)  # estado operacional atual; `cad` guarda o cadastro original
        ranking = self._ranking_ongs(doador, estado, categoria, armazenamento, ts)
        t_at = self.transportadores.iloc[self.ativos[ts.date()]]
        d_t = distancia_km(doador.lat, doador.lon, t_at["lat"].to_numpy(), t_at["lon"].to_numpy()) if len(t_at) else np.array([])
        perto = d_t <= P.RAIO_TRANSPORTADOR_KM
        base |= {
            "prioridade_regra": str(regra), "prioridade": str(prioridade),
            "hora": ts.hour, "dia_semana": ts.weekday(), "mes": ts.month, "fim_de_semana": ts.weekday() >= 5,
            "feriado": bool(ctx["feriado"]),
            "n_ongs_compativeis_10km": sum(1 for c in ranking if c["km"] <= 10),
            "dist_ong_top_km": round(ranking[0]["km"], 2) if ranking else None,
            "min_ate_receber_top": round(ranking[0]["min_receber"], 1) if ranking else None,
            "doador_pode_entregar": bool(doador.pode_entregar),
            "n_transportadores_ativos_raio": int(perto.sum()),
            "refrigerado_disponivel": bool(t_at["refrigerado"].to_numpy()[perto].any()) if len(t_at) else False,
            "doador_tem_refrigeracao": bool(doador.tem_refrigeracao),
        }
        limite = cad["validade_efetiva"] - timedelta(hours=P.MARGEM_CONSUMO_HORAS[categoria])
        extra: dict = {"n_ofertas_ong": 0, "escalado_admin": False, "rodadas_ong": 0, "rodadas_transporte": 0,
                       "orientado_refrigerar": False, "refrigerado_apos_orientacao": False}

        def descarte(motivo: str, t: datetime) -> dict:
            self._evento(lote_id, t, "DESCARTE", "sistema", motivo)
            return base | extra | {"status_final": "DESCARTADO", "descartado": True, "motivo_descarte": motivo}

        # --- Matching em rodadas (a rota expressa não tem tempo para uma 2ª rodada) ---
        t, idx = ts, None
        while True:
            extra["rodadas_ong"] += 1
            if t > ts:
                ranking = self._ranking_ongs(doador, estado, categoria, armazenamento, t)
                self._evento(lote_id, t, "NOVA_RODADA_ONG", "sistema", f"rodada={extra['rodadas_ong']}")
            if ranking:
                idx, t, n, escalou = self._oferecer_ongs(lote_id, ranking, prioridade, t)
                extra["n_ofertas_ong"] += n
                extra["escalado_admin"] |= escalou
            if idx is not None:
                break
            motivo = "SEM_ONG_ELEGIVEL" if extra["n_ofertas_ong"] == 0 else "NENHUMA_ONG_ACEITOU"
            if estado["rota_expressa"]:
                # Sem ONG a tempo: orientar a refrigeração (7.5). Se o doador refrigerar dentro
                # da janela segura, o lote sai da rota expressa e volta ao fluxo normal.
                extra["orientado_refrigerar"] = True
                self._evento(lote_id, t, "ORIENTACAO_REFRIGERAR", "sistema", "sem ONG viável na janela")
                t_ref = t + timedelta(minutes=float(rng.uniform(*P.TEMPO_ATE_REFRIGERAR_MIN)))
                if not (doador.tem_refrigeracao and rng.random() < P.PROB_DOADOR_REFRIGERA):
                    return descarte(motivo, t)
                try:
                    nova = validade_apos_refrigeracao(
                        categoria, estado["validade_efetiva"], t_ref,
                        preparo=cad["ts_preparo"], validade_rotulo=cad["validade_rotulo"],
                    )
                except LoteRecusado:
                    return descarte("REFRIGERADO_FORA_DA_JANELA", t_ref)
                armazenamento = Armazenamento.CONGELADO if categoria == Categoria.CONGELADO else Armazenamento.REFRIGERADO
                estado |= {"armazenamento": str(armazenamento), "validade_efetiva": nova, "rota_expressa": False}
                limite = nova - timedelta(hours=P.MARGEM_CONSUMO_HORAS[categoria])
                prioridade = prioridade_por_regra(categoria, armazenamento, nova - t_ref, cad["peso_kg"])
                extra |= {"refrigerado_apos_orientacao": True, "prioridade_operacional": str(prioridade)}
                self._evento(lote_id, t_ref, "REFRIGERADO_PELO_DOADOR", f"doador:{doador.doador_id}", str(prioridade))
                em_operacao = P.HORARIO_OPERACAO[0] <= _horas(t_ref) < P.HORARIO_OPERACAO[1]
                t = t_ref if em_operacao else self._proxima_rodada(t_ref)
                continue
            proxima = self._proxima_rodada(t)
            if proxima >= limite or extra["rodadas_ong"] >= P.MAX_RODADAS:
                return descarte(motivo, t)
            t = proxima

        ong = self.ongs_ok.iloc[idx]
        t_aceite = t
        escolhida = next((c for c in ranking if c["i"] == idx), None)
        extra |= {"ong_id": ong.ong_id, "ts_aceite_ong": t_aceite, "minutos_ate_match": round((t_aceite - ts) / MIN, 1),
                  "complementaridade": escolhida["complementaridade"] if escolhida else None,
                  "ong_tinha_pedido": escolhida["pedido"] if escolhida else None}
        if t_aceite >= limite:
            return descarte("VENCEU_AGUARDANDO_ONG", t_aceite)

        # --- Transporte em rodadas: gratuitos primeiro; pago só com espera estourada + risco alto ---
        km = float(distancia_km(doador.lat, doador.lon, ong.lat, ong.lon))
        espera = ESPERA_TRANSPORTE_GRATUITO[prioridade]
        janela = timedelta(minutes=P.JANELA_RODADA_TRANSPORTE_MIN)
        t, escolha, t_transp, pago = t_aceite, None, None, False
        while escolha is None:
            extra["rodadas_transporte"] += 1
            chuva = self._chuva(t)
            self._evento(lote_id, t, "OFERTA_TRANSPORTE", "sistema", f"{km:.1f}km rodada={extra['rodadas_transporte']}")
            vencedor, t_gratis = None, None
            for c in self._candidatos_gratuitos(doador, ong, km, categoria, armazenamento, cad["peso_kg"], t, chuva):
                if rng.random() < c[4]:
                    t_c = t + timedelta(minutes=float(rng.exponential(c[5])))
                    if t_c - t <= janela and (t_gratis is None or t_c < t_gratis):
                        vencedor, t_gratis = c, t_c

            if vencedor is not None and (espera is None or t_gratis - t <= espera):
                escolha, t_transp = vencedor, t_gratis
                break
            if espera is not None and "custo_caixa" not in extra:
                t_aprov = self._tentar_pago(lote_id, ong, km, categoria, armazenamento, prioridade,
                                            t + espera, espera, limite, chuva, extra)
                if t_aprov is not None and (t_gratis is None or t_aprov < t_gratis):
                    escolha, t_transp, pago = (Modalidade.APP_ENTREGA, "moto", False, None, 1.0, 0.0), t_aprov, True
                    break
            if vencedor is not None:
                escolha, t_transp = vencedor, t_gratis
                break
            proxima = self._proxima_rodada(t)
            if estado["rota_expressa"] or proxima >= limite or extra["rodadas_transporte"] >= P.MAX_RODADAS:
                return descarte("SEM_TRANSPORTE", min(max(t + janela, t_aceite), limite))
            t = proxima

        modalidade, veiculo, refrigerado, transp_id = escolha[0], escolha[1], escolha[2], escolha[3]
        ator_t = f"transportador:{transp_id}" if transp_id else str(modalidade)
        self._evento(lote_id, t_transp, "ACEITE_TRANSPORTE", ator_t, str(modalidade))
        chuva = self._chuva(t_transp)

        usa_hub = not estado["rota_expressa"] and (
            (TipoDoador(doador.tipo_doador) == TipoDoador.PF)
            or (modalidade in (Modalidade.MOTORISTA_RETORNO, Modalidade.TRANSPORTADORA) and rng.random() < 0.25)
        )
        hub_id = self._hub_mais_proximo(doador) if usa_hub else None

        if modalidade == Modalidade.DOADOR_ENTREGA:
            chegada = 0.0
        elif modalidade == Modalidade.APP_ENTREGA:
            chegada = rng.uniform(*P.APP_CHEGADA_MIN)
        else:
            chegada = rng.uniform(*P.CHEGADA_ATE_DOADOR_MIN) * (1.25 if chuva else 1.0)
        t_coleta = t_transp + timedelta(minutes=float(chegada))
        self._evento(lote_id, t_coleta, "COLETA", ator_t, hub_id or "porta_a_porta")

        minutos = self._minutos_trajeto(km, veiculo, t_coleta, chuva, estimada=False)
        if hub_id:
            minutos += rng.uniform(*P.ATRASO_HUB_MIN)
        # A ONG só recebe dentro da janela declarada (regras 6.4): fora dela, o lote espera.
        t_chegada = t_coleta + timedelta(minutes=float(minutos))
        t_entrega = proxima_abertura(t_chegada, float(ong.abertura_h), float(ong.fechamento_h))
        extra |= {
            "modalidade": str(modalidade), "transportador_id": transp_id, "hub_id": hub_id, "acionou_pago": pago,
            "ts_coleta": t_coleta, "minutos_trajeto": round(minutos, 1),
            "minutos_espera_janela": round((t_entrega - t_chegada) / MIN, 1),
        }

        limite_trajeto = trajeto_maximo(categoria, armazenamento, refrigerado)
        if limite_trajeto is not None and timedelta(minutes=minutos) > limite_trajeto:
            if rng.random() < P.PROB_DESCARTE_QUEBRA_CADEIA_FRIA:
                return descarte("QUEBRA_CADEIA_FRIA", t_entrega)
        if t_entrega > limite:
            return descarte("VENCEU_ANTES_DA_ENTREGA", t_entrega)

        # Inspeção na porta: quanto mais perto do vencimento, maior a chance de recusa.
        vida_total = estado["validade_efetiva"] - ts
        consumida = min(max((t_entrega - ts) / vida_total, 0.0), 1.0) if vida_total > timedelta(0) else 1.0
        p_recusa = (P.INSPECAO_BASE[categoria] + P.INSPECAO_FATOR[categoria] * consumida**2) * rng.lognormal(
            0, P.INSPECAO_SIGMA_QUALIDADE
        )
        if rng.random() < p_recusa:
            self._evento(lote_id, t_entrega, "RECUSA_INSPECAO", f"ong:{ong.ong_id}", f"vida_consumida={consumida:.2f}")
            return descarte("RECUSADO_NA_INSPECAO", t_entrega)

        self.ong_kg_dia[(ong.ong_id, t_entrega.date())] += cad["peso_kg"]
        extra["pedido_atendido"] = self._atender_pedido(ong.ong_id, categoria, t_entrega, cad["peso_kg"])
        self._evento(lote_id, t_entrega, "ENTREGA", ator_t, f"ong:{ong.ong_id}")
        return base | extra | {
            "status_final": "ENTREGUE", "descartado": False, "motivo_descarte": None, "ts_entrega": t_entrega,
            "refeicoes": round(refeicoes(categoria, cad["peso_kg"]), 1),
        }
