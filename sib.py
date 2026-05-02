import pandas as pd
import zipfile
import io
from pathlib import Path

# =============================
# CONFIGURAÇÃO
# =============================
BASE_DIR = Path(r"C:\dados_ans\dados_saneados")

# IMPORTANTE:
# 1) Filtra pelo nome do ZIP (evita pegar AMB_*_SAN.zip)
# 2) Ajuste o token "SIB" se seus arquivos usam outro padrão (ex.: "SIBBEN")
PADRAO_ZIP_SIB = "*SIB*_SAN.zip"

# Colunas mínimas para o exemplo (ajuste conforme sua análise real)
# Se MODALIDADE não existir no SIB, troque por CD_MODALIDADE / NM_MODALIDADE / etc.
COLUNA_AGREGAR = "MODALIDADE"

# Leitura em blocos (ajuste se quiser)
CHUNKSIZE = 200_000


# =============================
# LEITOR: CSV dentro do ZIP (em streaming)
# =============================
def iter_csv_from_san_zip(zip_path: Path, usecols=None, chunksize=CHUNKSIZE, encoding="latin-1", sep=";"):
    """
    Itera sobre chunks do CSV dentro de um *_SAN.zip, sem extrair no disco.
    """
    with zipfile.ZipFile(zip_path, "r") as z:
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]

        if len(csv_names) != 1:
            raise ValueError(f"ZIP inválido (esperado 1 CSV): {zip_path}")

        with z.open(csv_names[0]) as f:
            wrapper = io.TextIOWrapper(f, encoding=encoding)

            # dtype=str evita inferência (e alocações float64 desnecessárias)
            yield from pd.read_csv(
                wrapper,
                sep=sep,
                dtype=str,
                usecols=usecols,
                chunksize=chunksize,
                low_memory=False
            )


# =============================
# PROCESSAMENTO INCREMENTAL (sem estourar RAM)
# =============================
def processar_sib_incremental():
    arquivos = list(BASE_DIR.rglob(PADRAO_ZIP_SIB))

    # Filtra ainda mais, por segurança, para não pegar AMB/CIH por engano
    arquivos = [p for p in arquivos if "AMB_" not in p.name.upper() and "CIH_" not in p.name.upper()]

    if not arquivos:
        print(f"❌ Nenhum arquivo SIB saneado encontrado em: {BASE_DIR}")
        print(f"   Padrão usado: {PADRAO_ZIP_SIB}")
        return None

    print(f"🔍 {len(arquivos)} ZIPs SIB encontrados.\n")

    acumulador = {}  # chave -> contagem

    for zp in sorted(arquivos):
        print(f"➡ Processando {zp.name}")

        try:
            # lê apenas a coluna necessária
            for chunk in iter_csv_from_san_zip(zp, usecols=[COLUNA_AGREGAR]):
                # conta valores no chunk
                vc = chunk[COLUNA_AGREGAR].value_counts(dropna=False)
                for k, v in vc.items():
                    acumulador[k] = acumulador.get(k, 0) + int(v)

        except zipfile.BadZipFile as e:
            print(f"⚠ ZIP corrompido/ inválido (pulando): {zp.name} | {e}")
            continue
        except ValueError as e:
            print(f"⚠ Estrutura inesperada (pulando): {zp.name} | {e}")
            continue
        except KeyError:
            print(f"⚠ Coluna '{COLUNA_AGREGAR}' não encontrada em {zp.name}.")
            print("   Ajuste COLUNA_AGREGAR para o nome correto no seu SIB.")
            return None

    resumo = (
        pd.Series(acumulador, name="qt_beneficiarios")
        .reset_index()
        .rename(columns={"index": COLUNA_AGREGAR})
        .sort_values("qt_beneficiarios", ascending=False)
    )

    return resumo


def main():
    resumo = processar_sib_incremental()
    if resumo is None:
        return

    out = Path(r"C:\dados_ans\resumo_sib_modalidade.csv")
    resumo.to_csv(out, sep=";", index=False)
    print(f"\n✅ Resumo gerado: {out}")


if __name__ == "__main__":
    main()
