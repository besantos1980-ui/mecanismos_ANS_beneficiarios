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
    # ... (mantenha sua função de download anterior se precisar baixar novos)
    pass

def processar_sql():
    print("\n--- INICIANDO PROCESSAMENTO SQL ---")
    con = duckdb.connect()
    
    path_planos = os.path.join(DIRETORIO_BASE, "planos.csv")
    if not os.path.exists(path_planos):
        print(f"Erro: {path_planos} não encontrado.")
        return

    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine='xlsxwriter')

    con.execute(f"""
        CREATE OR REPLACE VIEW planos_base AS 
        SELECT * FROM read_csv_auto('{path_planos}', all_varchar=True, delim=';', encoding='latin-1') 
        WHERE COBERTURA = 'Assistência Médica'
    """)

    for ano in ANOS_INTERESSE:
        print(f"Buscando arquivos de {ano} no disco...")
        lista_cons = glob.glob(os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*CONS*.zip"), recursive=True)
        lista_det = glob.glob(os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*DET*.zip"), recursive=True)

        if not lista_cons or not lista_det:
            print(f"Aviso: Sem arquivos para o ano {ano}.")
            continue

        print(f"Processando {len(lista_cons)} estados de {ano}...")
        try:
            # SQL CORRIGIDO: parênteses ajustados nos filtros
            sql = f"""
                SELECT 
                    p.GR_CONTRATACAO, p.FATOR_MODERADOR, p.ACOMODACAO,
                    c.CD_MODALIDADE, c.CD_CARATER_ATENDIMENTO,
                    COUNT(DISTINCT c.ID_EVENTO_ATENCAO_SAUDE) as EVENTOS_UNICOS,
                    SUM(CAST(TRY_CAST(d.QT_ITEM_EVENTO_INFORMADO AS DOUBLE) AS DOUBLE)) as QTDE,
                    SUM(CAST(TRY_CAST(d.VL_ITEM_PAGO_FORNECEDOR AS DOUBLE) AS DOUBLE)) as VALOR
                FROM read_csv_auto({lista_cons}, all_varchar=True, union_by_name=True, delim=';', encoding='latin-1', ignore_errors=True) c
                JOIN read_csv_auto({lista_det}, all_varchar=True, union_by_name=True, delim=';', encoding='latin-1', ignore_errors=True) d 
                  ON c.ID_EVENTO_ATENCAO_SAUDE = d.ID_EVENTO_ATENCAO_SAUDE
                JOIN planos_base p ON c.ID_PLANO = p.ID_PLANO
                WHERE CAST(TRY_CAST(c.CD_MODALIDADE AS INTEGER) AS INTEGER) IN {MODALIDADES} 
                  AND CAST(TRY_CAST(c.CD_CARATER_ATENDIMENTO AS INTEGER) AS INTEGER) IN (1, 2)
                GROUP BY 1, 2, 3, 4, 5
            """
            df = con.execute(sql).df()
            if not df.empty:
                df.to_excel(writer, sheet_name=str(ano), index=False)
                print(f"Sucesso: Ano {ano} processado.")
            else:
                print(f"Aviso: Cruzamento vazio para {ano}.")
        except Exception as e:
            print(f"Erro no ano {ano}: {e}")

    writer.close()
    print(f"\nFim! Planilha gerada em: {ARQUIVO_SAIDA}")

# ESTA PARTE É OBRIGATÓRIA PARA O SCRIPT RODAR:
if __name__ == "__main__":
    processar_sql()
