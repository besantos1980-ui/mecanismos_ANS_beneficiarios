import os
import requests
import duckdb
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- CONFIGURAÇÕES DE CAMINHO ---
# Usamos o prefixo 'r' para que o Windows entenda as barras do caminho corretamente
DIRETORIO_BASE = r"C:\dados_ans" 
URL_AMBULATORIAL = "https://dadosabertos.ans.gov.br/FTP/PDA/TISS/AMBULATORIAL/"
URL_PLANOS = "https://dadosabertos.ans.gov.br/FTP/PDA/TISS/DADOS_DE_PLANOS/"
ARQUIVO_SAIDA = os.path.join(DIRETORIO_BASE, "Consolidado_Assistencial_ANS.xlsx")

ANOS_INTERESSE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
MODALIDADES = (22, 24, 25, 27, 28, 29)

def baixar_arquivos():
    """Faz o download dos arquivos ZIP da ANS para C:/dados_ans."""
    if not os.path.exists(DIRETORIO_BASE):
        os.makedirs(DIRETORIO_BASE)
        print(f"Pasta {DIRETORIO_BASE} criada.")

    print("Iniciando verificação de downloads na ANS...")
    try:
        response = requests.get(URL_AMBULATORIAL, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links_anos = [urljoin(URL_AMBULATORIAL, a['href']) for a in soup.find_all('a', href=True) 
                      if a['href'].endswith('/') and a['href'].strip('/').isdigit()]

        for url_ano in links_anos:
            ano_str = url_ano.strip('/').split('/')[-1]
            if int(ano_str) not in ANOS_INTERESSE:
                continue

            pasta_ano = os.path.join(DIRETORIO_BASE, "ambulatorial", ano_str)
            os.makedirs(pasta_ano, exist_ok=True)

            res_ano = requests.get(url_ano, timeout=30)
            soup_ano = BeautifulSoup(res_ano.text, 'html.parser')
            arquivos = [a['href'] for a in soup_ano.find_all('a', href=True) if a['href'].endswith('.zip')]

            for arquivo in arquivos:
                if "_REM_" in arquivo.upper(): continue # Ignora REM conforme sua regra
                
                caminho_local = os.path.join(pasta_ano, arquivo)
                if not os.path.exists(caminho_local):
                    print(f"Baixando: {arquivo}...")
                    with requests.get(urljoin(url_ano, arquivo), stream=True) as r:
                        with open(caminho_local, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=16384):
                                f.write(chunk)
    except Exception as e:
        print(f"Erro durante o download: {e}")

def processar_sql():
    """Processa os dados de C:/dados_ans usando DuckDB."""
    con = duckdb.connect()
    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine='xlsxwriter')
    
    # O script espera que o arquivo de planos esteja nesta pasta
    path_planos = os.path.join(DIRETORIO_BASE, "planos.csv")
    
    if not os.path.exists(path_planos):
        print(f"ERRO: O arquivo {path_planos} não foi encontrado!")
        print("Certifique-se de baixar a planilha de PLANOS e salvá-la como 'planos.csv' na pasta C:/dados_ans")
        return

    print("Processando dados com DuckDB SQL...")
    con.execute(f"CREATE OR REPLACE VIEW planos_base AS SELECT * FROM read_csv_auto('{path_planos}') WHERE COBERTURA = 'Assistência Médica'")

    for ano in ANOS_INTERESSE:
        path_cons = os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "*CONS*.zip")
        path_det = os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "*DET*.zip")
        
        print(f"Lendo arquivos de {ano}...")
        try:
            sql = f"""
                SELECT 
                    p.GR_CONTRATACAO, p.FATOR_MODERADOR, p.ACOMODACAO,
                    c.CD_MODALIDADE, c.CD_CARATER_ATENDIMENTO,
                    COUNT(DISTINCT c.ID_EVENTO_ATENCAO_SAUDE) as EVENTOS_UNICOS,
                    SUM(d.QT_ITEM_EVENTO_INFORMADO) as TOTAL_ITENS,
                    SUM(d.VL_ITEM_PAGO_FORNECEDOR) as TOTAL_VALOR
                FROM read_csv_auto('{path_cons}', ALL_VP=VOID) c
                JOIN read_csv_auto('{path_det}', ALL_VP=VOID) d ON c.ID_EVENTO_ATENCAO_SAUDE = d.ID_EVENTO_ATENCAO_SAUDE
                JOIN planos_base p ON c.ID_PLANO = p.ID_PLANO
                WHERE c.CD_MODALIDADE IN {MODALIDADES} AND c.CD_CARATER_ATENDIMENTO IN (1, 2)
                GROUP BY 1, 2, 3, 4, 5
            """
            df = con.execute(sql).df()
            df.to_excel(writer, sheet_name=str(ano), index=False)
        except Exception as e:
            print(f"Aviso: Não foi possível processar o ano {ano}. Erro: {e}")

    writer.close()
    print(f"\nConcluído! O arquivo Excel foi gerado em: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    # baixar_arquivos() # Execute uma vez para baixar tudo
    processar_sql()
