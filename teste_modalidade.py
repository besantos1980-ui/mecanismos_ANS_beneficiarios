import io
import zipfile
from pathlib import Path
import pandas as pd

BASE_DIR = Path(r"C:\dados_ans\dados_saneados")
OUTPUT = Path(r"C:\dados_ans\resumo_modalidade.csv")

ENCODING = "latin-1"
SEP = ";"
CHUNKSIZE = 200_000
COLUNA = "MODALIDADE"


def iter_csv_from_zip(zip_path: Path):
    with zipfile.ZipFile(zip_path, "r") as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            return
        with z.open(csvs[0]) as f:
            wrapper = io.TextIOWrapper(f, encoding=ENCODING)
            yield from pd.read_csv(
                wrapper,
                sep=SEP,
                dtype=str,
                chunksize=CHUNKSIZE,
                low_memory=False
            )


def main():
    arquivos = [
        p for p in BASE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".zip"
    ]

    print(f"🔍 {len(arquivos)} arquivos ZIP encontrados")

    acumulador = {}

    for zp in arquivos:
        print(f"➡ {zp.name}")
        for chunk in iter_csv_from_zip(zp):
            if COLUNA not in chunk.columns:
                continue

            vc = chunk[COLUNA].value_counts(dropna=False)
            for k, v in vc.items():
                acumulador[k] = acumulador.get(k, 0) + int(v)

    if not acumulador:
        print("❌ Nenhum dado com MODALIDADE foi encontrado.")
        return

    df = (
        pd.Series(acumulador, name="total")
        .reset_index()
        .rename(columns={"index": COLUNA})
        .sort_values("total", ascending=False)
    )

    df.to_csv(OUTPUT, sep=SEP, index=False)
    print(f"\n✅ Output gerado com sucesso:")
    print(OUTPUT)


if __name__ == "__main__":
    main()
