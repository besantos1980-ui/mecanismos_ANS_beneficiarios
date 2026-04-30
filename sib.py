import pandas as pd
import zipfile
import io
from pathlib import Path


from utils_zip import read_san_zip   # ou cole a função no próprio arquivo

def read_san_zip(zip_path: Path) -> pd.DataFrame:
    """
    Lê um arquivo *_SAN.zip contendo um único CSV e retorna DataFrame.
    """
    with zipfile.ZipFile(zip_path, "r") as z:
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]

        if len(csv_names) != 1:
            raise ValueError(f"ZIP inválido (esperado 1 CSV): {zip_path}")

        with z.open(csv_names[0]) as f:
            df = pd.read_csv(
                io.TextIOWrapper(f, encoding="latin-1"),
                sep=";",
                low_memory=False
            )
    return df

# =============================
# CONFIGURAÇÃO
# =============================
BASE_DIR = Path("dados_saneados")
PADRAO = "*SIB*_SAN.zip"

# =============================
# PIPELINE PRINCIPAL
# =============================
def processar_sib():
    arquivos = list(BASE_DIR.rglob(PADRAO))

    if not arquivos:
        print("❌ Nenhum arquivo SIB saneado encontrado.")
        return

    print(f"🔍 {len(arquivos)} arquivos SIB encontrados.\n")

    dfs = []

    for zp in arquivos:
        print(f"➡ Lendo {zp.name}")
        df = read_san_zip(zp)

        # ✅ A partir daqui, seus dados:
        # - já estão numericamente saneados
        # - sem vírgula decimal
        # - sem strings em colunas numéricas

        dfs.append(df)

    sib = pd.concat(dfs, ignore_index=True)

    print(f"✅ Base SIB consolidada: {len(sib):,} registros")

    return sib


def main():
    sib = processar_sib()

    if sib is None:
        return

    # ===== EXEMPLO DE USO =====
    # agregação simples (exemplo)
    resumo = (
        sib
        .groupby("MODALIDADE")
        .size()
        .reset_index(name="qt_beneficiarios")
    )

    resumo.to_csv("resumo_sib_modalidade.csv", sep=";", index=False)
    print("✅ Resumo gerado.")


if __name__ == "__main__":
    main()
