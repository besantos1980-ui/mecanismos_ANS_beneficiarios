import io
import zipfile
from pathlib import Path
import pandas as pd

# ============================================================
# CONFIGURAÇÃO (ajuste se necessário)
# ============================================================
BASE_DIR = Path(r"C:\dados_ans\dados_saneados")  # pasta FLAT

# Tokens aceitos para identificar arquivos de SIB pelo NOME do arquivo
# (se seus arquivos usam outro token, adicione aqui)
SIB_TOKENS = {"SIB", "BEN", "BENEF", "BENEFICIARIO", "BENEFICIARIOS"}

# Colunas candidatas para "modalidade" no SIB (fallback automático)
MODALIDADE_COL_CANDIDATAS = ["MODALIDADE", "NM_MODALIDADE", "CD_MODALIDADE"]

# Output
OUTPUT_CSV = Path(r"C:\dados_ans\resumo_sib_modalidade.csv")

# Leitura (streaming)
ENCODING = "latin-1"
SEP = ";"
CHUNKSIZE = 200_000

# Compactação (quando existirem _SAN.csv e não existirem _SAN.zip)
ZIP_COMPRESSLEVEL = 9
DELETE_CSV_AFTER_ZIP = False  # coloque True se quiser remover CSV após zipar


# ============================================================
# UTIL: cria ZIP limpo a partir de um *_SAN.csv (sem ZIP corrompido)
# ============================================================
def criar_zip_de_csv_saneado(csv_path: Path) -> Path:
    zip_path = csv_path.with_suffix(".zip")  # *_SAN.zip

    # Sempre recria do zero para evitar "Overlapped entries"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=ZIP_COMPRESSLEVEL
    ) as z:
        z.write(csv_path, arcname=csv_path.name)

    if DELETE_CSV_AFTER_ZIP:
        csv_path.unlink()

    return zip_path


# ============================================================
# UTIL: lista zips saneados (flat)
# ============================================================
def listar_san_zips() -> list[Path]:
    # estrutura flat: usar iterdir é mais rápido que rglob
    return sorted([
        p for p in BASE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".zip" and p.name.upper().endswith("_SAN.ZIP")
    ])


def listar_san_csvs() -> list[Path]:
    return sorted([
        p for p in BASE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".csv" and p.name.upper().endswith("_SAN.CSV")
    ])


# ============================================================
# UTIL: extrai tokens do nome do arquivo
# Ex.: "AC_201801_AMB_CONS_SAN.zip" -> {"AC","201801","AMB","CONS","SAN"}
# ============================================================
def tokens_do_nome(arquivo: Path) -> set[str]:
    nome = arquivo.stem  # sem ".zip"
    # se terminar com _SAN, remove esse sufixo lógico do stem
    if nome.upper().endswith("_SAN"):
        nome = nome[:-4]
    return set([t.upper() for t in nome.split("_") if t])


# ============================================================
# UTIL: inventário do que existe na pasta (para debug sem adivinhar)
# ============================================================
def inventario_datasets(zips: list[Path]) -> dict[str, int]:
    contagem = {}
    for z in zips:
        toks = tokens_do_nome(z)
        # heurística simples: dataset costuma ser um token curto (AMB/SIB/CIH/etc.)
        # aqui só contamos todos os tokens para você ver o que existe
        for t in toks:
            contagem[t] = contagem.get(t, 0) + 1
    # ordena por frequência
    return dict(sorted(contagem.items(), key=lambda kv: kv[1], reverse=True))


# ============================================================
# LEITOR: itera chunks do CSV dentro do ZIP (sem extrair no disco)
# ============================================================
def iter_csv_from_zip(zip_path: Path, usecols=None):
    with zipfile.ZipFile(zip_path, "r") as z:
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"ZIP inválido (esperado 1 CSV): {zip_path}")

        with z.open(csv_names[0]) as f:
            wrapper = io.TextIOWrapper(f, encoding=ENCODING)
            yield from pd.read_csv(
                wrapper,
                sep=SEP,
                dtype=str,          # evita inferência (economiza RAM)
                usecols=usecols,    # lê só o necessário
                chunksize=CHUNKSIZE,
                low_memory=False
            )


# ============================================================
# DETECTA QUAIS ZIPS PARECEM SER SIB
# ============================================================
def selecionar_zips_sib(zips: list[Path]) -> list[Path]:
    sibs = []
    for z in zips:
        toks = tokens_do_nome(z)
        if toks.intersection(SIB_TOKENS):
            sibs.append(z)
    return sorted(sibs)


# ============================================================
# PROCESSAMENTO INCREMENTAL (não estoura RAM)
# agrega por UF do arquivo + modalidade
# ============================================================
def processar_sib_incremental(zips_sib: list[Path]) -> pd.DataFrame:
    acumulador = {}  # (UF, modalidade) -> contagem

    for zp in zips_sib:
        # UF costuma ser o primeiro token (ex.: AC_201801_...)
        uf = zp.name.split("_", 1)[0].upper()

        # Descobrir qual coluna de modalidade existe, lendo apenas o cabeçalho (1o chunk)
        # Para isso, lemos um chunk pequeno sem usecols e detectamos colunas;
        # depois reprocessamos com usecols para ser leve.
        try:
            primeiro_chunk = next(iter_csv_from_zip(zp, usecols=None))
        except zipfile.BadZipFile as e:
            print(f"⚠ ZIP inválido (pulando): {zp.name} | {e}")
            continue

        cols = [c.upper() for c in primeiro_chunk.columns]
        col_modalidade = None
        for cand in MODALIDADE_COL_CANDIDATAS:
            if cand.upper() in cols:
                # pega o nome original (preserva case)
                col_modalidade = primeiro_chunk.columns[cols.index(cand.upper())]
                break

        if col_modalidade is None:
            print(f"❌ Nenhuma coluna de modalidade encontrada em {zp.name}. Colunas vistas: {primeiro_chunk.columns.tolist()[:20]}")
            raise KeyError(" | ".join(MODALIDADE_COL_CANDIDATAS))

        # Agora processa de verdade, lendo só a coluna necessária
        print(f"➡ Processando {zp.name} | UF={uf} | coluna_modalidade={col_modalidade}")

        for chunk in iter_csv_from_zip(zp, usecols=[col_modalidade]):
            vc = chunk[col_modalidade].value_counts(dropna=False)
            for k, v in vc.items():
                chave = (uf, str(k))
                acumulador[chave] = acumulador.get(chave, 0) + int(v)

    # monta dataframe final
    if not acumulador:
        return pd.DataFrame(columns=["UF_ARQ", "MODALIDADE", "qt_beneficiarios"])

    out = (
        pd.Series(acumulador, name="qt_beneficiarios")
        .reset_index()
        .rename(columns={"level_0": "UF_ARQ", "level_1": "MODALIDADE"})
        .sort_values(["UF_ARQ", "qt_beneficiarios"], ascending=[True, False])
    )
    return out


# ============================================================
# MAIN
# ============================================================
def main():
    if not BASE_DIR.exists():
        print(f"❌ Pasta não existe: {BASE_DIR}")
        return

    # 1) Se ainda houver CSVs saneados soltos, cria ZIPs saneados automaticamente
    san_zips = listar_san_zips()
    san_csvs = listar_san_csvs()

    if not san_zips and san_csvs:
        print(f"ℹ Não encontrei *_SAN.zip, mas encontrei {len(san_csvs)} *_SAN.csv. Vou zipar automaticamente...")
        for csv in san_csvs:
            zp = criar_zip_de_csv_saneado(csv)
            print(f"✅ Criado: {zp.name}")
        san_zips = listar_san_zips()

    # 2) Se ainda não houver ZIPs saneados, não há nada a processar
    if not san_zips:
        print(f"❌ Nenhum *_SAN.zip encontrado em: {BASE_DIR}")
        return

    # 3) Seleciona apenas os que parecem SIB pelo nome (tokens)
    zips_sib = selecionar_zips_sib(san_zips)

    if not zips_sib:
        print(f"❌ Nenhum arquivo SIB saneado encontrado em: {BASE_DIR}")
        print("✅ INVENTÁRIO do que existe (tokens mais frequentes nos nomes):")
        inv = inventario_datasets(san_zips)
        # mostra top 30 tokens
        for t, c in list(inv.items())[:30]:
            print(f"   {t}: {c}")
        print("\n➡ Para sanar isso, basta adicionar em SIB_TOKENS o token que seus arquivos SIB realmente usam no nome.")
        print("   Ex.: se seus arquivos se chamam *_BENEF*_SAN.zip, adicione 'BENEF' ou 'BENEFICIARIOS' em SIB_TOKENS.")
        return

    # 4) Processa incremental
    resumo = processar_sib_incremental(zips_sib)
    if resumo.empty:
        print("⚠ Nada foi agregado (nenhum registro lido).")
        return

    # 5) Salva
    resumo.to_csv(OUTPUT_CSV, sep=SEP, index=False)
    print(f"\n✅ Resumo gerado: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
