"""O requirements do Streamlit Community Cloud é cópia fiel do que o container do dashboard usa."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _pacotes(*arquivos: str) -> set[str]:
    linhas = []
    for a in arquivos:
        linhas += (RAIZ / a).read_text(encoding="utf-8").splitlines()
    return {l.strip() for l in linhas if l.strip() and not l.lstrip().startswith(("#", "-r"))}


def test_requirements_do_streamlit_cloud_igual_ao_do_container():
    assert _pacotes("src/dashboard/requirements.txt") == _pacotes("requirements/base.txt", "requirements/dashboard.txt")


def test_todas_as_dependencias_tem_versao_fixada():
    for arquivo in (RAIZ / "requirements").glob("*.txt"):
        for pacote in _pacotes(str(arquivo.relative_to(RAIZ))):
            assert "==" in pacote, f"{arquivo.name}: {pacote} sem versão fixada (supply chain)"
