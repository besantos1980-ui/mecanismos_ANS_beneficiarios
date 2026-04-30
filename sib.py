from pathlib import Path
import pandas as pd

from utils_zip import read_san_zip   # ou cole a função no próprio arquivo

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
