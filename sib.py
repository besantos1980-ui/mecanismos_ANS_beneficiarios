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

# Anos de interesse conforme sua solicitação
ANOS_INTERESSE = [2018, 2019, 2020, 2021, 2022, 2023, 2024]

# Modalidades: 22, 24, 25, 27, 28 e 29
MODALIDADES = (22, 24, 25, 27, 28, 29)

def baixar_arquivos():
    """Faz o download recursivo (Ano > Estado) ignorando arquivos REM."""
    print("--- INICIANDO FASE DE DOWNLOAD RECURSIVO ---")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(URL_AMBULATORIAL, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Mapeia as pastas dos ANOS
        links_anos = [urljoin(URL_AMBULATORIAL, a['href']) for a in soup.find_all('a', href=True) 
                      if a.get_text().strip('/').isdigit() and int(a.get_text().strip('/')) in ANOS_INTERESSE]

        for url_ano in links_anos:
            ano_str = url_ano.strip('/').split('/')[-1]
            print(f"\nExplorando diretórios do Ano: {ano_str}")

            res_ano = requests.get(url_ano, headers=headers)
            soup_ano = BeautifulSoup(res_ano.text, 'html.parser')
            
            # Filtra links que parecem siglas de estados (pastas com 2 caracteres)
            links_estados = [urljoin(url_ano, a['href']) for a in soup_ano.find_all('a', href=True) 
                             if len(a.get_text().strip('/')) == 2]

            for url_estado in links_estados:
                estado_sigla = url_estado.strip('/').split('/')[-1]
                pasta_local = os.path.join(DIRETORIO_BASE, "ambulatorial", ano_str, estado_sigla)
                os.makedirs(pasta_local, exist_ok=True)

                res_estado = requests.get(url_estado, headers=headers)
                soup_estado = BeautifulSoup(res_estado.text, 'html.parser')
                zips = [a['href'] for a in soup_estado.find_all('a', href=True) if '.zip' in a['href'].lower()]

                for zip_file in zips:
                    if "_REM_" in zip_file.upper():
                        continue # Pula arquivos de remuneração conforme solicitado
                    
                    caminho_final = os.path.join(pasta_local, zip_file)
                    if not os.path.exists(caminho_final):
                        print(f"Baixando: {ano_str}/{estado_sigla} -> {zip_file}")
                        try:
                            r = requests.get(urljoin(url_estado, zip_file), stream=True, headers=headers)
                            r.raise_for_status()
                            with open(caminho_final, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=1024*1024): # 1MB chunks
                                    f.write(chunk)
                        except Exception as e:
                            print(f"Falha ao baixar {zip_file}: {e}")
    except Exception as e:
        print(f"Erro na conexão com o portal da ANS: {e}")

def processar_sql():
    """Processa os dados usando DuckDB com detecção robusta de formato."""
    print("\n--- INICIANDO PROCESSAMENTO SQL ---")
    con = duckdb.connect()
    
    path_planos = os.path.join(DIRETORIO_BASE, "planos.csv")
    if not os.path.exists(path_planos):
        print(f"ERRO: O arquivo {path_planos} não foi encontrado na pasta.")
        return

    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine='xlsxwriter')

    print("Carregando base de PLANOS...")
    # Usamos read_csv_auto para detectar se o planos.csv é delimitado por , ou ;
    con.execute(f"""
        CREATE OR REPLACE VIEW planos_base AS 
        SELECT * FROM read_csv_auto('{path_planos}', all_varchar=True, ignore_errors=True) 
        WHERE COBERTURA = 'Assistência Médica'
    """)

    for ano in ANOS_INTERESSE:
        print(f"\nBuscando arquivos de {ano} no disco...")
        
        # Coleta a lista de caminhos físicos dos arquivos ZIP
        lista_cons = glob.glob(os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*CONS*.zip"), recursive=True)
        lista_det = glob.glob(os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*DET*.zip"), recursive=True)

        if not lista_cons or not lista_det:
            print(f"Aviso: Nenhum arquivo CONS/DET encontrado para o ano {ano}. Pulando...")
            continue

        print(f"Processando {len(lista_cons)} arquivos de estados para o ano {ano}...")
        try:
            # SQL Final: Try_Cast para evitar erros em dados sujos e ignore_errors para pular linhas ruins
            sql = f"""
                SELECT 
                    p.GR_CONTRATACAO, 
                    p.FATOR_MODERADOR, 
                    p.ACOMODACAO,
                    c.CD_MODALIDADE, 
                    c.CD_CARATER_ATENDIMENTO,
                    COUNT(DISTINCT c.ID_EVENTO_ATENCAO_SAUDE) as EVENTOS_UNICOS,
                    SUM(CAST(TRY_CAST(d.QT_ITEM_EVENTO_INFORMADO AS DOUBLE) AS DOUBLE)) as SOMA_QTDE,
                    SUM(CAST(TRY_CAST(d.VL_ITEM_PAGO_FORNECEDOR AS DOUBLE) AS DOUBLE)) as SOMA_VALOR_PAGO
                FROM read_csv_auto({lista_cons}, all_varchar=True, union_by_name=True, ignore_errors=True, null_padding=True) c
                JOIN read_csv_auto({lista_det}, all_varchar=True, union_by_name=True, ignore_errors=True, null_padding=True) d 
                  ON c.ID_EVENTO_ATENCAO_SAUDE = d.ID_EVENTO_ATENCAO_SAUDE
                JOIN planos_base p ON c.ID_PLANO = p.ID_PLANO
                WHERE CAST(TRY_CAST(c.CD_MODALIDADE AS INTEGER) AS INTEGER) IN {MODALIDADES} 
                  AND CAST(TRY_CAST(c.CD_CARATER_ATENDIMENTO AS INTEGER) AS INTEGER) IN (1, 2)
                GROUP BY 1, 2, 3, 4, 5
            """
            df = con.execute(sql).df()
            
            if not df.empty:
                df.to_excel(writer, sheet_name=str(ano), index=False)
                print(f"Sucesso: Dados de {ano} consolidados na planilha.")
            else:
                print(f"Aviso: O cruzamento do ano {ano} não gerou resultados.")
                
        except Exception as e:
            print(f"Erro ao processar o ano {ano}: {e}")

    writer.close()
    print(f"\n--- PROCESSO CONCLUÍDO ---")
    print(f"Relatório gerado em: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    # Como você já baixou os arquivos, a linha abaixo pode seguir comentada.
    # baixar_arquivos() 
    processar_sql()
