"""Curadoria do IPVS 2022 (Fundação SEADE) para o recorte da Rede Alimenta IA.

Fonte: Índice Paulista de Vulnerabilidade Social (IPVS) 2022, por setor censitário.
https://repositorio.seade.gov.br/dataset/2be01068-49cc-4cc1-85b8-38bd867aefc4

Saídas (versionadas no repositório):
    data/reference/setores_rmsp.csv  -> um setor censitário por linha, com região, grupo IPVS e centroide
    data/reference/regioes.csv       -> indicador de vulnerabilidade agregado por região

Uso:
    python -m src.data.curadoria_ipvs
"""

from __future__ import annotations

import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import shapefile  # pyshp

RAIZ = Path(__file__).resolve().parents[2]
DIR_RAW = RAIZ / "data" / "raw"
DIR_REF = RAIZ / "data" / "reference"

URL_IPVS = (
    "https://repositorio.seade.gov.br/dataset/2be01068-49cc-4cc1-85b8-38bd867aefc4"
    "/resource/35c74698-a368-4f0c-8f14-3694896a9d74/download/ipvs_2022.zip"
)
# Integridade da fonte: se o arquivo publicado mudar, a curadoria para e avisa
# em vez de gerar dados silenciosamente diferentes.
SHA256_IPVS = "0ec1284ad5666f6b6511458d517e7ca126e68a0299c72e28346cb71820defa8f"

MUNICIPIOS = {
    "3550308": "São Paulo",
    "3518800": "Guarulhos",
    "3534401": "Osasco",
    "3547809": "Santo André",
    "3548708": "São Bernardo do Campo",
    "3548807": "São Caetano do Sul",
    "3513801": "Diadema",
    "3529401": "Mauá",
}
COD_SAO_PAULO = "3550308"

# Distritos -> subprefeitura -> macrorregião, conforme a divisão administrativa
# da Prefeitura de São Paulo (8 macrorregiões).
SUBPREFEITURAS_SP: dict[str, tuple[str, list[str]]] = {
    "Sé": ("SP - Centro", ["Bela Vista", "Bom Retiro", "Cambuci", "Consolação", "Liberdade", "República", "Santa Cecília", "Sé"]),
    "Butantã": ("SP - Oeste", ["Butantã", "Morumbi", "Raposo Tavares", "Rio Pequeno", "Vila Sônia"]),
    "Lapa": ("SP - Oeste", ["Barra Funda", "Jaguara", "Jaguaré", "Lapa", "Perdizes", "Vila Leopoldina"]),
    "Pinheiros": ("SP - Oeste", ["Alto de Pinheiros", "Itaim Bibi", "Jardim Paulista", "Pinheiros"]),
    "Santana/Tucuruvi": ("SP - Norte 1", ["Santana", "Tucuruvi", "Mandaqui"]),
    "Jaçanã/Tremembé": ("SP - Norte 1", ["Jaçanã", "Tremembé"]),
    "Vila Maria/Vila Guilherme": ("SP - Norte 1", ["Vila Maria", "Vila Guilherme", "Vila Medeiros"]),
    "Perus": ("SP - Norte 2", ["Anhanguera", "Perus"]),
    "Pirituba/Jaraguá": ("SP - Norte 2", ["Jaraguá", "Pirituba", "São Domingos"]),
    "Freguesia/Brasilândia": ("SP - Norte 2", ["Brasilândia", "Freguesia do Ó"]),
    "Casa Verde/Cachoeirinha": ("SP - Norte 2", ["Casa Verde", "Cachoeirinha", "Limão"]),
    "Vila Mariana": ("SP - Sul 1", ["Moema", "Saúde", "Vila Mariana"]),
    "Ipiranga": ("SP - Sul 1", ["Cursino", "Ipiranga", "Sacomã"]),
    "Jabaquara": ("SP - Sul 1", ["Jabaquara"]),
    "Santo Amaro": ("SP - Sul 2", ["Campo Belo", "Campo Grande", "Santo Amaro"]),
    "Cidade Ademar": ("SP - Sul 2", ["Cidade Ademar", "Pedreira"]),
    "Campo Limpo": ("SP - Sul 2", ["Campo Limpo", "Capão Redondo", "Vila Andrade"]),
    "M'Boi Mirim": ("SP - Sul 2", ["Jardim Ângela", "Jardim São Luís"]),
    "Capela do Socorro": ("SP - Sul 2", ["Cidade Dutra", "Grajaú", "Socorro"]),
    "Parelheiros": ("SP - Sul 2", ["Marsilac", "Parelheiros"]),
    "Mooca": ("SP - Leste 1", ["Água Rasa", "Belém", "Brás", "Mooca", "Pari", "Tatuapé"]),
    "Aricanduva/Formosa/Carrão": ("SP - Leste 1", ["Aricanduva", "Carrão", "Vila Formosa"]),
    "Vila Prudente": ("SP - Leste 1", ["São Lucas", "Vila Prudente"]),
    "Sapopemba": ("SP - Leste 1", ["Sapopemba"]),
    "Penha": ("SP - Leste 1", ["Artur Alvim", "Cangaiba", "Penha", "Vila Matilde"]),
    "Ermelino Matarazzo": ("SP - Leste 2", ["Ermelino Matarazzo", "Ponte Rasa"]),
    "São Miguel": ("SP - Leste 2", ["Jardim Helena", "São Miguel", "Vila Jacuí"]),
    "Itaim Paulista": ("SP - Leste 2", ["Itaim Paulista", "Vila Curuçá"]),
    "Guaianases": ("SP - Leste 2", ["Guaianases", "Lajeado"]),
    "Itaquera": ("SP - Leste 2", ["Cidade Lider", "Itaquera", "José Bonifácio", "Parque do Carmo"]),
    "São Mateus": ("SP - Leste 2", ["Iguatemi", "São Mateus", "São Rafael"]),
    "Cidade Tiradentes": ("SP - Leste 2", ["Cidade Tiradentes"]),
}

GRUPOS_VULNERAVEIS = {5, 6}  # Alta e Muito Alta Vulnerabilidade


def _distrito_para_subprefeitura() -> dict[str, tuple[str, str]]:
    mapa = {}
    for subpref, (regiao, distritos) in SUBPREFEITURAS_SP.items():
        for distrito in distritos:
            mapa[distrito] = (subpref, regiao)
    return mapa


def baixar_ipvs(destino: Path = DIR_RAW / "ipvs_2022.zip") -> Path:
    """Baixa o zip do IPVS (se ainda não existir) e valida o SHA-256."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.exists():
        print(f"Baixando {URL_IPVS} ...")
        urllib.request.urlretrieve(URL_IPVS, destino)  # nosec B310 - URL fixa, HTTPS, validada por hash abaixo

    sha = hashlib.sha256(destino.read_bytes()).hexdigest()
    if sha != SHA256_IPVS:
        raise ValueError(
            f"SHA-256 inesperado para {destino.name}: {sha}. "
            "A fonte foi alterada ou o download está corrompido; revise antes de prosseguir."
        )
    return destino


def _centroide(pontos: list[tuple[float, float]]) -> tuple[float, float]:
    """Centroide de polígono (fórmula do shoelace) do anel externo; cai para a média se a área for nula."""
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pontos, pontos[1:] + pontos[:1]):
        cruz = x0 * y1 - x1 * y0
        area += cruz
        cx += (x0 + x1) * cruz
        cy += (y0 + y1) * cruz
    if abs(area) < 1e-15:
        xs, ys = zip(*pontos)
        return sum(xs) / len(xs), sum(ys) / len(ys)
    area *= 0.5
    return cx / (6 * area), cy / (6 * area)


def ler_setores(zip_path: Path) -> pd.DataFrame:
    """Lê o shapefile direto do zip e devolve os setores dos municípios do recorte."""
    with zipfile.ZipFile(zip_path) as z:
        leitor = shapefile.Reader(
            shp=io.BytesIO(z.read("IPVS_2022.shp")),
            shx=io.BytesIO(z.read("IPVS_2022.shx")),
            dbf=io.BytesIO(z.read("IPVS_2022.dbf")),
            encoding="utf-8",
        )
        linhas = []
        for sr in leitor.iterShapeRecords():
            rec = sr.record
            if rec["CD_MUN"] not in MUNICIPIOS:
                continue
            forma = sr.shape
            fim_anel = forma.parts[1] if len(forma.parts) > 1 else len(forma.points)
            lon, lat = _centroide(forma.points[:fim_anel])
            linhas.append(
                {
                    "cd_setor": rec["CD_SETOR"],
                    "cd_mun": rec["CD_MUN"],
                    "municipio": rec["NM_MUN"],
                    "distrito": rec["NM_DIST"],
                    "situacao": rec["SITUACAO"] or None,
                    "ipvs_grupo": int(rec["C_IPVS"]) if rec["C_IPVS"] else None,
                    "ipvs_nome": rec["N_IPVS"],
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                }
            )
    df = pd.DataFrame(linhas)
    df["ipvs_grupo"] = df["ipvs_grupo"].astype("Int64")
    return df


def atribuir_regioes(setores: pd.DataFrame) -> pd.DataFrame:
    mapa = _distrito_para_subprefeitura()
    df = setores.copy()
    em_sp = df["cd_mun"] == COD_SAO_PAULO

    faltantes = set(df.loc[em_sp, "distrito"]) - set(mapa)
    if faltantes:
        raise ValueError(f"Distritos de SP sem mapeamento para subprefeitura: {sorted(faltantes)}")

    df["subprefeitura"] = df["distrito"].map(lambda d: mapa.get(d, (None, None))[0]).where(em_sp)
    df["regiao"] = df["distrito"].map(lambda d: mapa.get(d, (None, None))[1]).where(em_sp, df["municipio"])
    return df


def agregar_regioes(setores: pd.DataFrame) -> pd.DataFrame:
    """% de setores classificados nos grupos 5 e 6, por região.

    Limitação documentada: o arquivo da SEADE não traz população por setor, então
    a proporção é de setores (proxy razoável: o IBGE dimensiona os setores com
    número de domicílios semelhante).
    """
    classificados = setores.dropna(subset=["ipvs_grupo"])
    agg = (
        classificados.assign(vulneravel=classificados["ipvs_grupo"].isin(GRUPOS_VULNERAVEIS))
        .groupby("regiao")
        .agg(
            municipio=("municipio", "first"),
            setores_classificados=("cd_setor", "size"),
            setores_vulneraveis=("vulneravel", "sum"),
            ipvs_medio=("ipvs_grupo", "mean"),
            lat=("lat", "mean"),
            lon=("lon", "mean"),
        )
        .reset_index()
    )
    agg["pct_vulneravel"] = (agg["setores_vulneraveis"] / agg["setores_classificados"]).round(4)
    # Índice 0-1 usado no ranking de ONGs (seção 6.1 das regras): normalização min-max.
    faixa = agg["pct_vulneravel"].max() - agg["pct_vulneravel"].min()
    agg["indice_vulnerabilidade"] = ((agg["pct_vulneravel"] - agg["pct_vulneravel"].min()) / faixa).round(4)
    agg[["ipvs_medio", "lat", "lon"]] = agg[["ipvs_medio", "lat", "lon"]].round(4)
    return agg.sort_values("pct_vulneravel", ascending=False).reset_index(drop=True)


def main() -> None:
    zip_path = baixar_ipvs()
    setores = atribuir_regioes(ler_setores(zip_path))
    regioes = agregar_regioes(setores)

    DIR_REF.mkdir(parents=True, exist_ok=True)
    setores.to_csv(DIR_REF / "setores_rmsp.csv", index=False)
    regioes.to_csv(DIR_REF / "regioes.csv", index=False)

    print(f"{len(setores)} setores | {len(regioes)} regiões")
    print(regioes[["regiao", "setores_classificados", "pct_vulneravel", "indice_vulnerabilidade"]].to_string(index=False))


if __name__ == "__main__":
    main()
