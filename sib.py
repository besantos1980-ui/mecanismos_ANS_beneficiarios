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
    """Faz o download dos arquivos ZIP da ANS para C:/dados_ans com seletor refinado."""
    print("--- INICIANDO FASE DE DOWNLOAD ---")
    if not os.path.exists(DIRETORIO_BASE):
        os.makedirs(DIRETORIO_BASE)

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(URL_AMBULATORIAL, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Pega todos os links da página
        links = soup.find_all('a', href=True)
        
        # Filtra apenas os que são números de anos de interesse
        anos_disponiveis = []
        for l in links:
            txt = l.get_text().replace('/', '').strip()
            if txt.isdigit() and int(txt) in ANOS_INTERESSE:
                anos_disponiveis.append((txt, urljoin(URL_AMBULATORIAL, l['href'])))

        if not anos_disponiveis:
            print("Não encontrei pastas de anos. Verifique se o link da ANS mudou.")
            return

        for ano_str, url_ano in anos_disponiveis:
            print(f"\nVerificando ano: {ano_str}...")
            pasta_ano = os.path.join(DIRETORIO_BASE, "ambulatorial", ano_str)
            os.makedirs(pasta_ano, exist_ok=True)

            res_ano = requests.get(url_ano, headers=headers, timeout=30)
            soup_ano = BeautifulSoup(res_ano.text, 'html.parser')
            
            # Busca todos os links que contém '.zip' no nome ou no href
            links_arquivos = soup_ano.find_all('a', href=True)
            zip_encontrados = [l['href'] for l in links_arquivos if '.zip' in l['href'].lower()]

            if not zip_encontrados:
                print(f"Nenhum arquivo ZIP listado para o ano {ano_str}.")
                continue

            for zip_name in zip_encontrados:
                # Remove caminhos relativos se existirem
                zip_clean = zip_name.split('/')[-1]
                
                if "_REM_" in zip_clean.upper():
                    continue
                
                caminho_local = os.path.join(pasta_ano, zip_clean)
                
                if not os.path.exists(caminho_local):
                    url_download = urljoin(url_ano, zip_name)
                    print(f"Iniciando download: {zip_clean}")
                    try:
                        with requests.get(url_download, stream=True, headers=headers) as r:
                            r.raise_for_status()
                            with open(caminho_local, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=128*1024): # 128KB chunks
                                    f.write(chunk)
                        print(f"Concluído: {zip_clean}")
                    except Exception as e:
                        print(f"Erro ao baixar {zip_clean}: {e}")
                else:
                    print(f"Já existe: {zip_clean}")

    except Exception as e:
        print(f"Erro na conexão principal: {e}")

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
