import os
import requests
import duckdb
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import glob

# --- CONFIGURAÇÕES ---
DIRETORIO_BASE = r"C:\dados_ans" 
ARQUIVO_SAIDA = os.path.join(DIRETORIO_BASE, "Consolidado_Assistencial_ANS.xlsx")
ANOS_INTERESSE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
MODALIDADES = ('22', '24', '25', '27', '28', '29') # Mantidos como string para o JOIN

def processar_sql():
    print("\n--- INICIANDO PROCESSAMENTO SQL (LIMPEZA DE ASPAS) ---")
    con = duckdb.connect()
    
    path_planos = os.path.join(DIRETORIO_BASE, "planos.csv")
    if not os.path.exists(path_planos):
        print(f"ERRO: {path_planos} não encontrado.")
        return

    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine='xlsxwriter')

    print("Carregando base de PLANOS...")
    # Limpamos aspas e espaços das chaves de ID_PLANO na origem
    con.execute(f"""
        CREATE OR REPLACE VIEW planos_base AS 
        SELECT 
            TRIM(REPLACE(ID_PLANO, '"', '')) as ID_PLANO,
            TRIM(REPLACE(GR_CONTRATACAO, '"', '')) as GR_CONTRATACAO,
            TRIM(REPLACE(FATOR_MODERADOR, '"', '')) as FATOR_MODERADOR,
            TRIM(REPLACE(ACOMODACAO, '"', '')) as ACOMODACAO,
            TRIM(REPLACE(COBERTURA, '"', '')) as COBERTURA
        FROM read_csv_auto('{path_planos}', all_varchar=True, ignore_errors=True) 
        WHERE TRIM(REPLACE(COBERTURA, '"', '')) = 'Assistência Médica'
    """)

    for ano in ANOS_INTERESSE:
        print(f"\n--- Processando Ano: {ano} ---")
        lista_cons = glob.glob(os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*CONS*.zip"), recursive=True)
        
        if not lista_cons:
            print(f"Aviso: Sem arquivos para {ano}.")
            continue

        resultados_ano = []

        for f_cons in lista_cons:
            f_det = f_cons.replace("CONS", "DET")
            if not os.path.exists(f_det): continue

            try:
                # SQL CORRIGIDO: Limpa aspas das colunas de ligação e filtros
                sql = f"""
                    SELECT 
                        p.GR_CONTRATACAO, 
                        p.FATOR_MODERADOR, 
                        p.ACOMODACAO,
                        TRIM(REPLACE(c.CD_MODALIDADE, '"', '')) as CD_MODALIDADE, 
                        TRIM(REPLACE(c.CD_CARATER_ATENDIMENTO, '"', '')) as CD_CARATER_ATENDIMENTO,
                        COUNT(DISTINCT TRIM(REPLACE(c.ID_EVENTO_ATENCAO_SAUDE, '"', ''))) as EVENTOS,
                        SUM(CAST(TRY_CAST(REPLACE(REPLACE(d.QT_ITEM_EVENTO_INFORMADO, '"', ''), ',', '.') AS DOUBLE) AS DOUBLE)) as QTDE,
                        SUM(CAST(TRY_CAST(REPLACE(REPLACE(d.VL_ITEM_PAGO_FORNECEDOR, '"', ''), ',', '.') AS DOUBLE) AS DOUBLE)) as VALOR
                    FROM read_csv_auto('{f_cons}', all_varchar=True, ignore_errors=True, union_by_name=True) c
                    JOIN read_csv_auto('{f_det}', all_varchar=True, ignore_errors=True, union_by_name=True) d 
                      ON TRIM(REPLACE(c.ID_EVENTO_ATENCAO_SAUDE, '"', '')) = TRIM(REPLACE(d.ID_EVENTO_ATENCAO_SAUDE, '"', ''))
                    JOIN planos_base p 
                      ON TRIM(REPLACE(c.ID_PLANO, '"', '')) = p.ID_PLANO
                    WHERE TRIM(REPLACE(c.CD_MODALIDADE, '"', '')) IN {MODALIDADES} 
                      AND TRIM(REPLACE(c.CD_CARATER_ATENDIMENTO, '"', '')) IN ('1', '2')
                    GROUP BY 1, 2, 3, 4, 5
                """
                res = con.execute(sql).df()
                if not res.empty:
                    resultados_ano.append(res)
            except Exception as e:
                continue

        if resultados_ano:
            df_final_ano = pd.concat(resultados_ano).groupby(
                ['GR_CONTRATACAO', 'FATOR_MODERADOR', 'ACOMODACAO', 'CD_MODALIDADE', 'CD_CARATER_ATENDIMENTO']
            ).sum().reset_index()
            
            df_final_ano.to_excel(writer, sheet_name=str(ano), index=False)
            print(f"Sucesso: Ano {ano} consolidado.")
        else:
            print(f"Aviso: Nenhuma informação válida para {ano}.")

    writer.close()
    print(f"\n--- PROCESSO CONCLUÍDO ---")
    print(f"Relatório final: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    processar_sql()
