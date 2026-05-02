import io
import zipfile
from pathlib import Path
import pandas as pd

# ============================================================
# CONFIGURAÇÃO
# ============================================================
BASE_DIR = Path(r"C:\dados_ans\dados_saneados")

# coluna que você quer agregar (ajuste se necessário)
COLUNA_AGREGAR = "MODALIDADE"

# leitura
ENCODING = "latin-1"
SEP = ";"
CHUNKSIZE = 200_000

# saída
OUTPUT = Path(r"C:\dados_ans\resumo_agregado.csv")


# ============================================================
# LEITOR: CSV de dentro do ZIP (streaming)
# ============================================================
def iter_csv_from_zip(zip_path: Path):
    with zipfile.ZipFile(zip_path, "r") as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]

        if not csvs:
            raise ValueError(f"ZIP sem CSV: {zip_path}")

        if len(csvs) > 1:
            raise ValueError(f"ZIP com mais de um CSV: {zip_path}")

        with z.open(csvs[0]) as f:
            wrapper = io.TextIOWrapper(f, encoding=ENCODING)
            yield from pd.read_csv(
                wrapper,
                sep=SEP,
                dtype=str,          # NÃO inferir tipos
                chunksize=CHUNKSIZE,
                low_memory=False
            )


# ============================================================
# PIPELINE PRINCIPAL — LÊ TUDO
# ============================================================
def processar_tudo():
    # pega TODOS os arquivos zip saneados (sem exceção)
    arquivos = [
        p for p in BASE_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".zip"
        and p.name.upper().endswith("_SAN.ZIP")
    ]

    if not arquivos:
        print(f"❌ Nenhum *_SAN.zip encontrado em {BASE_DIR}")
        return None

    print(f"🔍 {len(arquivos)} arquivos saneados encontrados.\n")

    acumulador = {}

    for zp in sorted(arquivos):
        print(f"➡ Lendo {zp.name}")

        try:
            for chunk in iter_csv_from_zip(zp):
                if COLUNA_AGREGAR not in chunk.columns:
                    # simplesmente ignora arquivos que não têm a coluna
                    continue

                vc = chunk[COLUNA_AGREGAR].value_counts(dropna=False)
                for k, v in vc.items():
                    acumulador[k] = acumulador.get(k, 0) + int(v)

        except zipfile.BadZipFile as e:
            print(f"⚠ ZIP inválido ignorado: {zp.name} | {e}")
            continue

    if not acumulador:
        print(f"⚠ Nenhum dado encontrado para coluna '{COLUNA_AGREGAR}'.")
        return None

    resumo = (
        pd.Series(acumulador, name="total")
        .reset_index()
        .rename(columns={"index": COLUNA_AGREGAR})
        .sort_values("total", ascending=False)
    )

    return resumo


# ============================================================
# MAIN
# ============================================================
def main():
    resultado = processar_tudo()
    if resultado is None:
        return

    resultado.to_csv(OUTPUT, sep=SEP, index=False)
    print(f"\n✅ Resultado gerado com sucesso:")
    print(OUTPUT)


if __name__ == "__main__":
    main()
