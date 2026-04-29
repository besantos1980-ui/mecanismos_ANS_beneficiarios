import pandas as pd
import numpy as np
import zipfile
from pathlib import Path
import io

# =============================
# CONFIGURAÇÃO
# =============================
INPUT_DIR = Path("dados_originais")   # aqui ficam os .zip
OUTPUT_DIR = Path("dados_saneados")
OUTPUT_DIR.mkdir(exist_ok=True)

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
    original = series.copy()

    s = (
        series.astype(str)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan})
        .str.replace(r"^,", "0.", regex=True)
        .str.replace(",", ".", regex=False)
    )

    numeric = pd.to_numeric(s, errors="coerce")

    if target_type == "int":
        return numeric.round(0).astype("Int64"), original
    else:
        return numeric.astype("float"), original


def sanitize_dataframe(df, numeric_columns, dataset_name):
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
        pd.concat(inconsistencies).to_csv(
            OUTPUT_DIR / f"inconsistencias_{dataset_name}.csv",
            sep=";",
            index=False
        )

    return df


# =============================
# PIPELINE ZIP → SAN
# =============================
def process_zip(zip_path: Path):
    print(f"➡ Processando ZIP: {zip_path.name}")

    with zipfile.ZipFile(zip_path, "r") as z:
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]

        if not csv_names:
            print("❌ ZIP sem CSV:", zip_path.name)
            return

        csv_name = csv_names[0]

        with z.open(csv_name) as f:
            df = pd.read_csv(
                io.TextIOWrapper(f, encoding="latin-1"),
                sep=";",
                dtype=str,
                low_memory=False
            )

    if "_DET" in csv_name.upper():
        df = sanitize_dataframe(df, NUMERIC_COLUMNS_DET, csv_name)
    else:
        df = sanitize_dataframe(df, NUMERIC_COLUMNS_CONS, csv_name)

    output_file = OUTPUT_DIR / csv_name.replace(".csv", "_SAN.csv")
    df.to_csv(output_file, sep=";", index=False)

    print(f"✅ Gerado: {output_file.name}")
    print("-" * 60)


def main():
    zips = list(INPUT_DIR.glob("*.zip"))

    if not zips:
        print("❌ Nenhum ZIP encontrado.")
        return

    for zp in zips:
        process_zip(zp)

    print("✅ Saneamento concluído.")


if __name__ == "__main__":
    main()
