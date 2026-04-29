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
ARQUIVO_SAIDA = os.path.join(DIRETORIO_BASE, "Consolidado_Assistencial_ANS.xlsx")

ANOS_INTERESSE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
MODALIDADES = (22, 24, 25, 27, 28, 29)

# =========================
# Extrair TXT do ZIP
# =========================
def extrair_txt(zip_path):
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            nomes = [n for n in z.namelist() if n.lower().endswith(".txt")]
            if not nomes:
                return None
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            tmp.write(z.read(nomes[0]))
            tmp.close()
            return tmp.name
    except Exception:
        return None

# =========================
# PROCESSAMENTO
# =========================
def processar_sql():
    print("\n--- INICIANDO PROCESSAMENTO SQL ---")
    con = duckdb.connect()
    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine="xlsxwriter")

    for ano in ANOS_INTERESSE:
        print(f"\n--- Processando Ano: {ano} ---")

        lista_cons = glob.glob(
            os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*CONS*.zip"),
            recursive=True
        )

        if not lista_cons:
            print(f"Aviso: Sem arquivos encontrados para o ano {ano}.")
            continue

        resultados = []
        arquivos_ok = 0

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
                    WITH cons AS (
                        SELECT
                            COALESCE(
                                ID_EVENTO_ATENCAO_SAUDE,
                                ID_EVENTO_ATENCAO
                            ) AS ID_EVENTO,
                            TRY_CAST(CD_MODALIDADE AS INTEGER) AS CD_MODALIDADE,
                            TRY_CAST(CD_CARATER_ATENDIMENTO AS INTEGER) AS CD_CARATER_ATENDIMENTO
                        FROM read_csv(
                            '{cons_txt}',
                            delim='|',
                            header=True,
                            encoding='latin1',
                            ignore_errors=True
                        )
                    ),
                    det AS (
                        SELECT
                            COALESCE(
                                ID_EVENTO_ATENCAO_SAUDE,
                                ID_EVENTO_ATENCAO
                            ) AS ID_EVENTO,
                            TRY_CAST(QT_ITEM_EVENTO_INFORMADO AS DOUBLE) AS QTDE,
                            TRY_CAST(VL_ITEM_PAGO_FORNECEDOR AS DOUBLE) AS VALOR
                        FROM read_csv(
                            '{det_txt}',
                            delim='|',
                            header=True,
                            encoding='latin1',
                            ignore_errors=True
                        )
                    )
                    SELECT
                        c.CD_MODALIDADE,
                        c.CD_CARATER_ATENDIMENTO,
                        COUNT(DISTINCT c.ID_EVENTO) AS EVENTOS,
                        SUM(d.QTDE) AS QTDE,
                        SUM(d.VALOR) AS VALOR
                    FROM cons c
                    JOIN det d
                      ON c.ID_EVENTO = d.ID_EVENTO
                    WHERE c.CD_MODALIDADE IN {MODALIDADES}
                      AND c.CD_CARATER_ATENDIMENTO IN (1, 2)
                    GROUP BY 1,2
                """

                df = con.execute(sql).df()
                if not df.empty:
                    resultados.append(df)
                    arquivos_ok += 1

            except Exception:
                continue

        if resultados:
            df_final = (
                pd.concat(resultados)
                .groupby(
                    ["CD_MODALIDADE", "CD_CARATER_ATENDIMENTO"],
                    as_index=False
                )
                .sum()
            )

            df_final.to_excel(writer, sheet_name=str(ano), index=False)
            print(f"Sucesso: {arquivos_ok} arquivos válidos no ano {ano}.")
        else:
            print(f"Aviso: Nenhum dado válido no ano {ano}.")

    writer.close()
    print("\n--- PROCESSO CONCLUÍDO ---")
    print(f"Arquivo gerado em: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    processar_sql()
