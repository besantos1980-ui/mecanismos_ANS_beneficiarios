import zipfile
from pathlib import Path

# =============================
# CONFIGURAÇÃO
# =============================
BASE_DIR = Path("dados_saneados")   # onde estão os CSVs saneados
DELETE_CSV_AFTER_ZIP = False       # MUDE PARA False se quiser manter os CSVs

# =============================
# PIPELINE DE COMPACTAÇÃO
# =============================
def zip_csv(csv_path: Path):
    zip_path = csv_path.with_suffix(".zip")

    if zip_path.exists():
        print(f"⏩ ZIP já existe, pulando: {zip_path.name}")
        return

    print(f"📦 Zipando: {csv_path.name}")

    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9
    ) as z:
        z.write(csv_path, arcname=csv_path.name)

    if DELETE_CSV_AFTER_ZIP:
        csv_path.unlink()
        print(f"🗑 CSV removido: {csv_path.name}")

    print(f"✅ Gerado: {zip_path.name}")
    print("-" * 70)


def main():
    csvs = list(BASE_DIR.rglob("*_SAN.csv"))

    if not csvs:
        print("❌ Nenhum CSV saneado encontrado.")
        return

    print(f"🔍 {len(csvs)} CSVs saneados encontrados.\n")

    for csv in csvs:
        zip_csv(csv)

    print("✅ Compactação concluída com sucesso.")


if __name__ == "__main__":
    main()
