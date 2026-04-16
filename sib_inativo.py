import pandas as pd
import os
import glob
from datetime import datetime

print(f"[{datetime.now().strftime('%H:%M:%S')}] --- Iniciando Processamento Pesado (30GB+) ---")

def processar_sib_csv_incremental(caminho_csv):
    nome_base = os.path.basename(caminho_csv)
    uf = nome_base.split('_')[-1].split('.')[0]
    
    # Criar uma pasta para organizar os resultados desta UF
    pasta_saida = f"resultados_{uf}"
    if not os.path.exists(pasta_saida):
        os.makedirs(pasta_saida)
    
    print(f"Os arquivos de saída serão salvos na pasta: {os.path.abspath(pasta_saida)}")

    # Configuração de Trimestres (2018 a 2025)
    trimestres = []
    for ano in range(2018, 2026):
        for t in range(1, 5):
            nome_arquivo = f"{t}T{ano}_{uf}.csv"
            q_start = pd.Timestamp(year=ano, month=(t-1)*3 + 1, day=1)
            q_end = q_start + pd.offsets.QuarterEnd(0)
            trimestres.append({
                'nome': nome_arquivo, 
                'caminho': os.path.join(pasta_saida, nome_arquivo),
                'start': q_start, 
                'end': q_end
            })

    colunas_preservar = ['REGISTRO_OPERADORA', 'DT_NASCIMENTO', 'CD_PLANO_RPS', 'CD_MUNICIPIO', 'SG_UF']
    colunas_datas = ['DT_CONTRATACAO', 'DT_REATIVACAO', 'DT_CANCELAMENTO']
    
    total_linhas_lidas = 0

    try:
        # Lendo em blocos (Chunks)
        chunk_iter = pd.read_csv(caminho_csv, sep=';', chunksize=200000, 
                                 dtype=str, encoding='utf-8', on_bad_lines='skip')

        for i, chunk in enumerate(chunk_iter):
            total_linhas_lidas += len(chunk)
            
            if i % 5 == 0:
                print(f"Progresso: {total_linhas_lidas:,} linhas processadas...")

            # Conversão de datas
            for col in colunas_datas:
                chunk[col] = pd.to_datetime(chunk[col], errors='coerce')
            
            chunk['DT_INICIO_EFETIVO'] = chunk['DT_REATIVACAO'].combine_first(chunk['DT_CONTRATACAO'])
            chunk = chunk.dropna(subset=['DT_INICIO_EFETIVO'])

            for q in trimestres:
                condicao_ativo = (chunk['DT_INICIO_EFETIVO'] <= q['end']) & \
                                 (chunk['DT_CANCELAMENTO'] >= q['start'])
                
                df_ativo = chunk.loc[condicao_ativo, colunas_preservar]
                
                if not df_ativo.empty:
                    # GRAVAÇÃO IMEDIATA (Modo Append 'a')
                    # Se o arquivo não existe, escreve o cabeçalho. Se existe, apenas anexa.
                    file_exists = os.path.isfile(q['caminho'])
                    df_ativo.to_csv(q['caminho'], mode='a', index=False, 
                                    header=not file_exists, sep=';', encoding='utf-8')

        print(f"\nCONCLUÍDO! Total de linhas lidas: {total_linhas_lidas:,}")
        print(f"Verifique a pasta '{pasta_saida}' para encontrar os arquivos por trimestre.")

    except Exception as e:
        print(f"ERRO CRÍTICO: {e}")

# --- Execução ---
# Lembre-se de ajustar o caminho para a sua pasta do OneDrive se necessário
arquivos_csv = glob.glob("sib_inativo_*.csv") 
# No final do seu script sib_inativo.py
import os
import glob

# Use o caminho real da sua pasta do OneDrive
caminho_local = r"C:\Users\bruno.santos\OneDrive - ABRAMGE\Beneficiários_SIB" 

# O script vai procurar todos os CSVs dentro dessa pasta específica
arquivos_csv = glob.glob(os.path.join(caminho_local, "sib_inativo_*.csv"))

if not arquivos_csv:
    print(f"Aviso: Nenhum arquivo encontrado em {caminho_local}")
else:
    for csv in arquivos_csv:
        processar_sib_trimestral(csv)
if not arquivos_csv:
    print("Nenhum arquivo CSV encontrado para processar.")
else:
    for f in arquivos_csv:
        processar_sib_csv_incremental(f)
