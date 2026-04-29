import pandas as pd
import numpy as np
from pathlib import Path

# =============================
# CONFIGURAÇÃO
# =============================
INPUT_DIR = Path("dados_originais")
OUTPUT_DIR = Path("dados_saneados")
OUTPUT_DIR.mkdir(exist_ok=True)

# Colunas esperadas por tipo
NUMERIC_COLUMNS_DET = {
    "QT_ITEM_EVENTO_INFORMADO": "int",
    "VL_ITEM_EVENTO_INFORMADO": "float",
    "VL_ITEM_PAGO_FORNECEDOR": "float"
}

NUMERIC_COLUMNS_CONS = {
    "LG_VALOR_PREESTABELECIDO": "int"
}

# =============================
# FUNÇÕES DE SANEAMENTO
# =============================
def normalize_numeric(series: pd.Series, target_type: str):
    """
    Normaliza números com vírgula decimal, strings vazias e valores inválidos.
    """
    original = series.copy()

    # Padroniza string
    s = (
        series.astype(str)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan})
    )

    # Corrige casos ",71" → "0.71"
    s = s.str.replace(r"^,", "0.", regex=True)

    # Vírgula decimal → ponto
    s = s.str.replace(",", ".", regex=False)

    # Converte
    numeric = pd.to_numeric(s, errors="coerce")

    if target_type == "int":
        return numeric.round(0).astype("Int64"), original
    else:
        return numeric.astype("float"), original


def sanitize_dataframe(df: pd.DataFrame, numeric_columns: dict, dataset_name: str):
    inconsistencies = []

    for col, target_type in numeric_columns.items():
        if col not in df.columns:
            continue

        sane, original = normalize_numeric(df[col], target_type)

        mask_invalid = sane.isna() & original.notna()

        if mask_invalid.any():
            inconsistencies.append(
                df.loc[mask_invalid, ["ID_EVENTO_ATENCAO_SAUDE", col]]
                .assign(valor_original=original[mask_invalid])
            )

        df[col] = sane

    if inconsistencies:
        inconsistencies_df = pd.concat(inconsistencies, ignore_index=True)
        inconsistencies_df.to_csv(
            OUTPUT_DIR / f"inconsistencias_{dataset_name}.csv",
            index=False,
            sep=";"
        )

    return df


# =============================
# PIPELINE PRINCIPAL
# =============================
def process_file(file_path: Path):
    print(f"➡ Processando: {file_path.name}")

    df = pd.read_csv(
        file_path,
        sep=";",
        dtype=str,
        low_memory=False
    )

    if "_DET" in file_path.name:
        df = sanitize_dataframe(df, NUMERIC_COLUMNS_DET, file_path.stem)
    else:
        df = sanitize_dataframe(df, NUMERIC_COLUMNS_CONS, file_path.stem)

    output_file = OUTPUT_DIR / file_path.name.replace(".csv", "_SAN.csv")
    df.to_csv(output_file, sep=";", index=False)

    print(f"✅ Arquivo saneado: {output_file.name}")
    print("-" * 60)


def main():
    files = list(INPUT_DIR.glob("*.csv"))

    if not files:
        print("❌ Nenhum arquivo encontrado.")
        return

    for file in files:
        process_file(file)

    print("✅ Saneamento finalizado com sucesso.")


if __name__ == "__main__":
    main()
