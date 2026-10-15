"""Gera chaves de API para a demonstração: as chaves em claro vão para `segredos/` (fora do Git) e
o JSON com os SHA-256 vai para a variável `REDE_ALIMENTA_CHAVES_API` (segredo da plataforma de deploy).

Uso:
    python -m src.api.chaves doador:D-0008 doador:D-0211 ong:O-005 admin:A-01
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys

from src.data.curadoria_ipvs import RAIZ


def main(identidades: list[str]) -> None:
    cadastro, claras = {}, []
    for ident in identidades:
        papel, id_ = ident.split(":")
        chave = f"ra_{papel}_{secrets.token_urlsafe(24)}"
        cadastro[hashlib.sha256(chave.encode()).hexdigest()] = {"papel": papel, "id": id_}
        claras.append(f"{ident}\t{chave}")
    destino = RAIZ / "segredos" / "chaves-api.txt"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text("\n".join(claras) + "\n", encoding="utf-8")
    print(f"Chaves em claro salvas em {destino.relative_to(RAIZ)} (NÃO versionar).")
    print("Valor de REDE_ALIMENTA_CHAVES_API (só hashes):")
    print(json.dumps(cadastro, separators=(",", ":")))


if __name__ == "__main__":
    main(sys.argv[1:] or ["doador:D-0008", "doador:D-0211", "ong:O-005", "admin:A-01"])
