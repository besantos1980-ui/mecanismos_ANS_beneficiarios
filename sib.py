import os
import glob
import zipfile
import tempfile
import duckdb
import pandas as pd

# =========================
# CONFIGURAÇÕES
# =========================
DIRETORIO_BASE = r"C:\dados_ans"
URL_AMBULATORIAL = "https://dadosabertos.ans.gov.br/FTP/PDA/TISS/AMBULATORIAL/"
ARQUIVO_SAIDA = os.path.join(DIRETORIO_BASE, "Consolidado_Assistencial_ANS.xlsx")

ANOS_INTERESSE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
MODALIDADES = (22, 24, 25, 27, 28, 29)

# =========================
# FUNÇÃO: extrair TXT do ZIP
# =========================
def extrair_txt(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            nomes = [n for n in z.namelist() if n.lower().endswith('.txt')]
            if not nomes:
                return None

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            tmp.write(z.read(nomes[0]))
            tmp.close()
            return tmp.name
    except Exception:
        return None

# =========================
# PROCESSAMENTO PRINCIPAL
# =========================
def processar_sql():
    print("\n--- INICIANDO PROCESSAMENTO SQL ---")
    con = duckdb.connect()

    path_planos = os.path.join(DIRETORIO_BASE, "planos.csv")
    if not os.path.exists(path_planos):
        print(f"ERRO: {path_planos} não encontrado.")
        return

    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine="xlsxwriter")

    print("Carregando base de PLANOS...")
    con.execute(f"""
        CREATE OR REPLACE VIEW planos_base AS
        SELECT *
        FROM read_csv(
            '{path_planos}',
            header=True,
            delim=';',
            encoding='latin-1',
            ignore_errors=True,
            all_varchar=True
        )
        WHERE COBERTURA = 'Assistência Médica'
    """)

    for ano in ANOS_INTERESSE:
        print(f"\n--- Processando Ano: {ano} ---")

        lista_cons = glob.glob(
            os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*CONS*.zip"),
            recursive=True
        )

        if not lista_cons:
            print(f"Aviso: Sem arquivos encontrados para o ano {ano}.")
            continue

        resultados_ano = []
        arquivos_validos = 0

        for f_cons in lista_cons:
            f_det = f_cons.replace("CONS", "DET")

            if not os.path.exists(f_det):
                continue

            cons_txt = extrair_txt(f_cons)
            det_txt = extrair_txt(f_det)

            if not cons_txt or not det_txt:
                continue

            try:
                sql = f"""
                    SELECT
                        p.GR_CONTRATACAO,
                        p.FATOR_MODERADOR,
                        p.ACOMODACAO,
                        TRY_CAST(c.CD_MODALIDADE AS INTEGER) AS CD_MODALIDADE,
                        TRY_CAST(c.CD_CARATER_ATENDIMENTO AS INTEGER) AS CD_CARATER_ATENDIMENTO,
                        COUNT(DISTINCT c.ID_EVENTO_ATENCAO_SAUDE) AS EVENTOS,
                        SUM(TRY_CAST(d.QT_ITEM_EVENTO_INFORMADO AS DOUBLE)) AS QTDE,
                        SUM(TRY_CAST(d.VL_ITEM_PAGO_FORNECEDOR AS DOUBLE)) AS VALOR
                    FROM read_csv(
                        '{cons_txt}',
                        header=True,
                        delim='|',
                        encoding='latin-1',
                        ignore_errors=True
                    ) c
                    JOIN read_csv(
                        '{det_txt}',
                        header=True,
                        delim='|',
                        encoding='latin-1',
                        ignore_errors=True
                    ) d
                      ON c.ID_EVENTO_ATENCAO_SAUDE = d.ID_EVENTO_ATENCAO_SAUDE
                    JOIN planos_base p
                      ON c.ID_PLANO = p.ID_PLANO
                    WHERE TRY_CAST(c.CD_MODALIDADE AS INTEGER) IN {MODALIDADES}
                      AND TRY_CAST(c.CD_CARATER_ATENDIMENTO AS INTEGER) IN (1, 2)
                    GROUP BY 1,2,3,4,5
                """

                df = con.execute(sql).df()

                if not df.empty:
                    resultados_ano.append(df)
                    arquivos_validos += 1

            except Exception:
                continue

        if resultados_ano:
            df_final_ano = (
                pd.concat(resultados_ano)
                .groupby(
                    [
                        "GR_CONTRATACAO",
                        "FATOR_MODERADOR",
                        "ACOMODACAO",
                        "CD_MODALIDADE",
                        "CD_CARATER_ATENDIMENTO"
                    ],
                    as_index=False
                )
                .sum()
            )

            df_final_ano.to_excel(writer, sheet_name=str(ano), index=False)
            print(f"Sucesso: Ano {ano} consolidado com {arquivos_validos} arquivos válidos.")
        else:
            print(f"Aviso: Nenhuma informação válida extraída para o ano {ano}.")

    writer.close()
    print("\n--- PROCESSO CONCLUÍDO ---")
    print(f"Relatório gerado em: {ARQUIVO_SAIDA}")

# =========================
# EXECUÇÃO
# =========================
if __name__ == "__main__":
    processar_sql()
