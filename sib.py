import os
import requests
import duckdb
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- CONFIGURAÇÕES ---
DIRETORIO_BASE = r"C:\dados_ans" 
URL_AMBULATORIAL = "https://dadosabertos.ans.gov.br/FTP/PDA/TISS/AMBULATORIAL/"
ARQUIVO_SAIDA = os.path.join(DIRETORIO_BASE, "Consolidado_Assistencial_ANS.xlsx")

ANOS_INTERESSE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
MODALIDADES = (22, 24, 25, 27, 28, 29)

def baixar_arquivos():
    """Faz o download dos arquivos ZIP da ANS para C:/dados_ans."""
    print("--- INICIANDO FASE DE DOWNLOAD ---")
    if not os.path.exists(DIRETORIO_BASE):
        os.makedirs(DIRETORIO_BASE)

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(URL_AMBULATORIAL, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Encontra os links das pastas de anos
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href'].strip('/')
            if href.isdigit() and int(href) in ANOS_INTERESSE:
                ano_str = href
                url_ano = urljoin(URL_AMBULATORIAL, href + '/')
                
                pasta_ano = os.path.join(DIRETORIO_BASE, "ambulatorial", ano_str)
                os.makedirs(pasta_ano, exist_ok=True)

                print(f"Verificando arquivos para o ano: {ano_str}...")
                res_ano = requests.get(url_ano, headers=headers, timeout=30)
                soup_ano = BeautifulSoup(res_ano.text, 'html.parser')
                
                # Procura por arquivos ZIP
                for a in soup_ano.find_all('a', href=True):
                    zip_name = a['href']
                    if zip_name.endswith('.zip') and "_REM_" not in zip_name.upper():
                        caminho_local = os.path.join(pasta_ano, zip_name)
                        
                        if not os.path.exists(caminho_local):
                            print(f"Baixando: {zip_name}")
                            with requests.get(urljoin(url_ano, zip_name), stream=True, headers=headers) as r:
                                with open(caminho_local, 'wb') as f:
                                    for chunk in r.iter_content(chunk_size=65536):
                                        f.write(chunk)
                        else:
                            print(f"Arquivo já existe: {zip_name}")
    except Exception as e:
        print(f"Erro no download: {e}")

def processar_sql():
    """Processa os dados usando DuckDB com as correções de parâmetros."""
    print("\n--- INICIANDO FASE DE PROCESSAMENTO SQL ---")
    con = duckdb.connect()
    
    path_planos = os.path.join(DIRETORIO_BASE, "planos.csv")
    if not os.path.exists(path_planos):
        print(f"ERRO CRÍTICO: Salve o arquivo 'planos.csv' em {DIRETORIO_BASE} antes de continuar.")
        return

    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine='xlsxwriter')

    # Criar a visão de planos
    con.execute(f"""
        CREATE OR REPLACE VIEW planos_base AS 
        SELECT * FROM read_csv_auto('{path_planos}', all_varchar=True) 
        WHERE COBERTURA = 'Assistência Médica'
    """)

    for ano in ANOS_INTERESSE:
        # Padrões de busca para os arquivos baixados
        path_cons = os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "*CONS*.zip")
        path_det = os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "*DET*.zip")
        
        # Verifica se os arquivos realmente existem na pasta antes de rodar o SQL
        if not os.path.exists(os.path.dirname(path_cons)):
            print(f"Aviso: Pasta do ano {ano} não encontrada. Pulando...")
            continue

        print(f"Processando ano {ano} (isso pode demorar conforme o tamanho dos arquivos)...")
        try:
            sql = f"""
                SELECT 
                    p.GR_CONTRATACAO, p.FATOR_MODERADOR, p.ACOMODACAO,
                    c.CD_MODALIDADE, c.CD_CARATER_ATENDIMENTO,
                    COUNT(DISTINCT c.ID_EVENTO_ATENCAO_SAUDE) as EVENTOS_UNICOS,
                    SUM(CAST(d.QT_ITEM_EVENTO_INFORMADO AS DOUBLE)) as TOTAL_ITENS,
                    SUM(CAST(d.VL_ITEM_PAGO_FORNECEDOR AS DOUBLE)) as TOTAL_VALOR
                FROM read_csv_auto('{path_cons}', all_varchar=True, union_by_name=True) c
                JOIN read_csv_auto('{path_det}', all_varchar=True, union_by_name=True) d 
                  ON c.ID_EVENTO_ATENCAO_SAUDE = d.ID_EVENTO_ATENCAO_SAUDE
                JOIN planos_base p ON c.ID_PLANO = p.ID_PLANO
                WHERE CAST(c.CD_MODALIDADE AS INTEGER) IN {MODALIDADES} 
                  AND CAST(c.CD_CARATER_ATENDIMENTO AS INTEGER) IN (1, 2)
                GROUP BY 1, 2, 3, 4, 5
            """
            df = con.execute(sql).df()
            
            if not df.empty:
                df.to_excel(writer, sheet_name=str(ano), index=False)
                print(f"Sucesso: Ano {ano} gravado no Excel.")
            else:
                print(f"Aviso: Sem dados correspondentes para o ano {ano}.")
                
        except Exception as e:
            print(f"Falha ao processar o ano {ano}: {e}")

    writer.close()
    print(f"\nRELATÓRIO FINALIZADO: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    baixar_arquivos() # AGORA ATIVO
    processar_sql()
