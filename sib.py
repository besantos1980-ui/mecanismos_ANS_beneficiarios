import pandas as pd
import zipfile
import io
from pathlib import Path

# =============================
# CONFIGURAÇÃO
# =============================
BASE_DIR = Path(r"C:\dados_ans\dados_saneados")

# Filtro por nome do arquivo (layout flat)
PADRAO_DATASET = "SIB"   # token obrigatório no nome do ZIP

# Ajuste para o nome real da coluna no SIB, se necessário
COLUNA_AGREGAR = "MODALIDADE"

CHUNKSIZE = 200_000
ENCODING = "latin-1"
SEP = ";"


# =============================
# LEITOR DE CSV DENTRO DO ZIP
# =============================
def iter_csv_from_zip(zip_path: Path):
    """
    Itera sobre chunks do CSV contido em um ZIP saneado.
    Assume exatamente 1 CSV por ZIP.
    """
    with zipfile.ZipFile(zip_path, "r") as z:
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]

        if len(csv_names) != 1:
            raise ValueError(f"ZIP inválido (esperado 1 CSV): {zip_path}")

        with z.open(csv_names[0]) as f:
            wrapper = io.TextIOWrapper(f, encoding=ENCODING)
            yield from pd.read_csv(
                wrapper,
                sep=SEP,
                dtype=str,        # evita inferência e estouro de RAM
                chunksize=CHUNKSIZE,
                low_memory=False
            )


# =============================
# PROCESSAMENTO SIB (INCREMENTAL)
# =============================
def processar_sib_incremental():
    # Busca APENAS arquivos ZIP no diretório flat
    arquivos = [
        p for p in BASE_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".zip"
        and PADRAO_DATASET in p.name.upper()
    ]

    if not arquivos:
        print(f"❌ Nenhum arquivo SIB saneado encontrado em: {BASE_DIR}")
        return None

    print(f"🔍 {len(arquivos)} arquivos SIB encontrados.\n")

    acumulador = {}

    for zp in sorted(arquivos):
        print(f"➡ Processando {zp.name}")

        try:
            for chunk in iter_csv_from_zip(zp):
                if COLUNA_AGREGAR not in chunk.columns:
                    raise KeyError(COLUNA_AGREGAR)

                vc = chunk[COLUNA_AGREGAR].value_counts(dropna=False)
                for k, v in vc.items():
                    acumulador[k] = acumulador.get(k, 0) + int(v)

        except zipfile.BadZipFile as e:
            print(f"⚠ ZIP inválido, ignorado: {zp.name} | {e}")
            continue
        except KeyError as e:
            print(f"❌ Coluna '{e}' não encontrada em {zp.name}")
            return None

    resumo = (
        pd.Series(acumulador, name="qt_beneficiarios")
        .reset_index()
        .rename(columns={"index": COLUNA_AGREGAR})
        .sort_values("qt_beneficiarios", ascending=False)
    )

    return resumo


# =============================
# MAIN
# =============================
def main():
    resumo = processar_sib_incremental()
    if resumo is None:
        return

    output = Path(r"C:\dados_ans\resumo_sib_modalidade.csv")
    resumo.to_csv(output, sep=SEP, index=False)

    print(f"\n✅ Resumo SIB gerado com sucesso:")
    print(output)


if __name__ == "__main__":
    main()
