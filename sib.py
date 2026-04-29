import os
import requests
import duckdb
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import glob

# --- CONFIGURAÇÕES ---
DIRETORIO_BASE = r"C:\dados_ans" 
URL_AMBULATORIAL = "https://dadosabertos.ans.gov.br/FTP/PDA/TISS/AMBULATORIAL/"
ARQUIVO_SAIDA = os.path.join(DIRETORIO_BASE, "Consolidado_Assistencial_ANS.xlsx")

ANOS_INTERESSE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
MODALIDADES = (22, 24, 25, 27, 28, 29)

def baixar_arquivos():
    """Download recursivo mantido para referência."""
    # (Sua lógica de download já está concluída, pule para o processamento)
    pass

def processar_sql():
    print("\n--- INICIANDO PROCESSAMENTO SQL ---")
    con = duckdb.connect()
    
    path_planos = os.path.join(DIRETORIO_BASE, "planos.csv")
    if not os.path.exists(path_planos):
        print(f"ERRO: {path_planos} não encontrado.")
        return

    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine='xlsxwriter')

    print("Carregando base de PLANOS...")
    con.execute(f"""
        CREATE OR REPLACE VIEW planos_base AS 
        SELECT * FROM read_csv_auto('{path_planos}', all_varchar=True, ignore_errors=True) 
        WHERE COBERTURA = 'Assistência Médica'
    """)

    for ano in ANOS_INTERESSE:
        print(f"\n--- Processando Ano: {ano} ---")
        
        lista_cons = glob.glob(os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*CONS*.zip"), recursive=True)
        
        if not lista_cons:
            print(f"Aviso: Sem arquivos encontrados para o ano {ano}.")
            continue

        resultados_ano = []

        # Processamos ARQUIVO POR ARQUIVO para evitar erro de sniffing no lote
        for f_cons in lista_cons:
            f_det = f_cons.replace("CONS", "DET")
            
            if not os.path.exists(f_det):
                continue

            try:
                # Query para um único par de arquivos (CONS + DET)
                # Usamos try_cast e ignoramos erros por arquivo
                sql = f"""
                    SELECT 
                        p.GR_CONTRATACAO, 
                        p.FATOR_MODERADOR, 
                        p.ACOMODACAO,
                        c.CD_MODALIDADE, 
                        c.CD_CARATER_ATENDIMENTO,
                        COUNT(DISTINCT c.ID_EVENTO_ATENCAO_SAUDE) as EVENTOS,
                        SUM(CAST(TRY_CAST(d.QT_ITEM_EVENTO_INFORMADO AS DOUBLE) AS DOUBLE)) as QTDE,
                        SUM(CAST(TRY_CAST(d.VL_ITEM_PAGO_FORNECEDOR AS DOUBLE) AS DOUBLE)) as VALOR
                    FROM read_csv_auto('{f_cons}', all_varchar=True, ignore_errors=True, union_by_name=True) c
                    JOIN read_csv_auto('{f_det}', all_varchar=True, ignore_errors=True, union_by_name=True) d 
                      ON c.ID_EVENTO_ATENCAO_SAUDE = d.ID_EVENTO_ATENCAO_SAUDE
                    JOIN planos_base p ON c.ID_PLANO = p.ID_PLANO
                    WHERE CAST(TRY_CAST(c.CD_MODALIDADE AS INTEGER) AS INTEGER) IN {MODALIDADES} 
                      AND CAST(TRY_CAST(c.CD_CARATER_ATENDIMENTO AS INTEGER) AS INTEGER) IN (1, 2)
                    GROUP BY 1, 2, 3, 4, 5
                """
                res = con.execute(sql).df()
                if not res.empty:
                    resultados_ano.append(res)
            except Exception:
                # Se um arquivo específico falhar, ignoramos e passamos para o próximo
                continue

        if resultados_ano:
            # Consolida todos os pequenos dataframes do ano em um só
            df_final_ano = pd.concat(resultados_ano).groupby(
                ['GR_CONTRATACAO', 'FATOR_MODERADOR', 'ACOMODACAO', 'CD_MODALIDADE', 'CD_CARATER_ATENDIMENTO']
            ).sum().reset_index()
            
            df_final_ano.to_excel(writer, sheet_name=str(ano), index=False)
            print(f"Sucesso: Ano {ano} consolidado com {len(resultados_ano)} arquivos.")
        else:
            print(f"Aviso: Nenhuma informação válida extraída para o ano {ano}.")

    writer.close()
    print(f"\n--- PROCESSO CONCLUÍDO ---")
    print(f"Relatório gerado em: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    processar_sql()
