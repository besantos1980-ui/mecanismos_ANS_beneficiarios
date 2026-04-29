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
    print("--- INICIANDO FASE DE DOWNLOAD RECURSIVO ---")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(URL_AMBULATORIAL, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Mapeia as pastas dos ANOS
        links_anos = [urljoin(URL_AMBULATORIAL, a['href']) for a in soup.find_all('a', href=True) 
                      if a.get_text().strip('/').isdigit() and int(a.get_text().strip('/')) in ANOS_INTERESSE]

        for url_ano in links_anos:
            ano_str = url_ano.strip('/').split('/')[-1]
            print(f"\nExplorando Ano: {ano_str}")

            # 2. Entra no ano e mapeia as pastas dos ESTADOS (AC, SP, RJ...)
            res_ano = requests.get(url_ano, headers=headers)
            soup_ano = BeautifulSoup(res_ano.text, 'html.parser')
            links_estados = [urljoin(url_ano, a['href']) for a in soup_ano.find_all('a', href=True) 
                             if len(a.get_text().strip('/')) == 2] # Pastas de estados têm 2 letras

            for url_estado in links_estados:
                estado_sigla = url_estado.strip('/').split('/')[-1]
                pasta_local = os.path.join(DIRETORIO_BASE, "ambulatorial", ano_str, estado_sigla)
                os.makedirs(pasta_local, exist_ok=True)

                # 3. Lista e baixa os arquivos ZIP dentro da pasta do Estado
                res_estado = requests.get(url_estado, headers=headers)
                soup_estado = BeautifulSoup(res_estado.text, 'html.parser')
                zips = [a['href'] for a in soup_estado.find_all('a', href=True) if '.zip' in a['href'].lower()]

                for zip_file in zips:
                    if "_REM_" in zip_file.upper(): continue
                    
                    caminho_final = os.path.join(pasta_local, zip_file)
                    if not os.path.exists(caminho_final):
                        print(f"Baixando: {estado_sigla} -> {zip_file}")
                        try:
                            r = requests.get(urljoin(url_estado, zip_file), stream=True, headers=headers)
                            with open(caminho_final, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=1024*1024): # 1MB chunks
                                    f.write(chunk)
                        except Exception as e:
                            print(f"Erro no download {zip_file}: {e}")

    except Exception as e:
        print(f"Erro na conexão: {e}")

def processar_sql():
    print("\n--- INICIANDO PROCESSAMENTO SQL ---")
    con = duckdb.connect()
    
    path_planos = os.path.join(DIRETORIO_BASE, "planos.csv")
    if not os.path.exists(path_planos):
        print("Erro: planos.csv não encontrado.")
        return

    writer = pd.ExcelWriter(ARQUIVO_SAIDA, engine='xlsxwriter')

    # Carregando planos com detecção automática de encoding
    con.execute(f"""
        CREATE OR REPLACE VIEW planos_base AS 
        SELECT * FROM read_csv_auto('{path_planos}', all_varchar=True, ignore_errors=True) 
        WHERE COBERTURA = 'Assistência Médica'
    """)

    for ano in ANOS_INTERESSE:
        path_cons = os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*CONS*.zip")
        path_det = os.path.join(DIRETORIO_BASE, "ambulatorial", str(ano), "**", "*DET*.zip")
        
        print(f"Processando todos os estados de {ano} (isso pode levar alguns minutos)...")
        try:
            # Mudanças:
            # 1. Removido encoding fixo (usando auto-detect)
            # 2. ignore_errors=True para não travar em caracteres inválidos
            # 3. sample_size=-1 para melhorar a detecção em arquivos grandes
            sql = f"""
                SELECT 
                    p.GR_CONTRATACAO, p.FATOR_MODERADOR, p.ACOMODACAO,
                    c.CD_MODALIDADE, c.CD_CARATER_ATENDIMENTO,
                    COUNT(DISTINCT c.ID_EVENTO_ATENCAO_SAUDE) as EVENTOS_UNICOS,
                    SUM(CAST(TRY_CAST(d.QT_ITEM_EVENTO_INFORMADO AS DOUBLE) AS DOUBLE)) as QTDE,
                    SUM(CAST(TRY_CAST(d.VL_ITEM_PAGO_FORNECEDOR AS DOUBLE) AS DOUBLE)) as VALOR
                FROM read_csv_auto('{path_cons}', all_varchar=True, union_by_name=True, ignore_errors=True, sample_size=-1) c
                JOIN read_csv_auto('{path_det}', all_varchar=True, union_by_name=True, ignore_errors=True, sample_size=-1) d 
                  ON c.ID_EVENTO_ATENCAO_SAUDE = d.ID_EVENTO_ATENCAO_SAUDE
                JOIN planos_base p ON c.ID_PLANO = p.ID_PLANO
                WHERE CAST(TRY_CAST(c.CD_MODALIDADE AS INTEGER) AS INTEGER) IN {MODALIDADES} 
                  AND CAST(TRY_CAST(c.CD_CARATER_ATENDIMENTO AS INTEGER) AS INTEGER) IN (1, 2)
                GROUP BY 1, 2, 3, 4, 5
            """
            df = con.execute(sql).df()
            
            if not df.empty:
                df.to_excel(writer, sheet_name=str(ano), index=False)
                print(f"Sucesso: Ano {ano} processado e gravado.")
            else:
                print(f"Aviso: O cruzamento para o ano {ano} não retornou dados. Verifique se os IDs de planos batem.")
                
        except Exception as e:
            print(f"Erro no ano {ano}: {e}")

    writer.close()
    print(f"\nFim! Planilha gerada em: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    baixar_arquivos()
    processar_sql()
