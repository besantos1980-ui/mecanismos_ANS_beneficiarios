import pandas as pd
import os
import glob
from datetime import datetime

print(f"[{datetime.now().strftime('%H:%M:%S')}] --- Script Iniciado ---")

def processar_sib_trimestral(caminho_csv):
    # Extrai o nome da UF do arquivo (ex: sib_inativo_AC.csv -> AC)
    nome_base = os.path.basename(caminho_csv)
    uf = nome_base.split('_')[-1].split('.')[0]
    arquivo_saida = f"sib_processado_{uf}.xlsx"
    
    print(f"\nIniciando processamento do arquivo: {nome_base}")
    
    # Configuração de Trimestres (2018 a 2025)
    trimestres = []
    for ano in range(2018, 2026):
        for t in range(1, 5):
            nome_aba = f"{t}T{ano}"
            q_start = pd.Timestamp(year=ano, month=(t-1)*3 + 1, day=1)
            q_end = q_start + pd.offsets.QuarterEnd(0)
            trimestres.append({'nome': nome_aba, 'start': q_start, 'end': q_end})

    colunas_preservar = ['REGISTRO_OPERADORA', 'DT_NASCIMENTO', 'CD_PLANO_RPS', 'CD_MUNICIPIO', 'SG_UF']
    colunas_datas = ['DT_CONTRATACAO', 'DT_REATIVACAO', 'DT_CANCELAMENTO']
    
    total_linhas_lidas = 0
    acumulador = {t['nome']: [] for t in trimestres}

    try:
        # Lendo em blocos de 100k linhas para não estourar a RAM do Codespaces
        # Removido o compression='zip'
        chunk_iter = pd.read_csv(caminho_csv, sep=';', chunksize=100000, 
                                 dtype=str, encoding='utf-8', on_bad_lines='skip')

        for i, chunk in enumerate(chunk_iter):
            total_linhas_lidas += len(chunk)
            
            if i % 5 == 0: # Feedback a cada 500 mil linhas
                print(f"Linhas processadas: {total_linhas_lidas:,}...")

            # Converter colunas para data
            for col in colunas_datas:
                chunk[col] = pd.to_datetime(chunk[col], errors='coerce')
            
            # Lógica: Se houver reativação, ela manda. Se não, usa contratação.
            chunk['DT_INICIO_EFETIVO'] = chunk['DT_REATIVACAO'].combine_first(chunk['DT_CONTRATACAO'])
            
            # Remove quem não tem data de início (dados corrompidos ou vazios)
            chunk = chunk.dropna(subset=['DT_INICIO_EFETIVO'])

            for q in trimestres:
                # Condição de estar ativo: começou antes do fim do tri E cancelou depois do início do tri
                condicao_ativo = (chunk['DT_INICIO_EFETIVO'] <= q['end']) & \
                                 (chunk['DT_CANCELAMENTO'] >= q['start'])
                
                df_ativo = chunk.loc[condicao_ativo, colunas_preservar]
                
                if not df_ativo.empty:
                    acumulador[q['nome']].append(df_ativo)

        print(f"Fim da leitura. Total de linhas no CSV: {total_linhas_lidas:,}")
        print("Gerando abas do Excel (isso pode demorar um pouco)...")

        with pd.ExcelWriter(arquivo_saida, engine='xlsxwriter') as writer:
            for nome_aba, lista_dfs in acumulador.items():
                if lista_dfs:
                    df_final_aba = pd.concat(lista_dfs).drop_duplicates()
                    
                    # Limite do Excel é 1.048.576 linhas
                    if len(df_final_aba) > 1048000:
                        df_final_aba = df_final_aba.iloc[:1048000]
                        print(f" ! Aba {nome_aba} atingiu o limite do Excel e foi truncada.")
                    
                    df_final_aba.to_excel(writer, sheet_name=nome_aba, index=False)
                    print(f" + Aba {nome_aba} ok ({len(df_final_aba)} registros)")

        print(f"\nSUCESSO: Arquivo '{arquivo_saida}' criado!")

    except Exception as e:
        print(f"ERRO CRÍTICO: {e}")

# --- Busca arquivos .csv na pasta raiz ---
arquivos_csv = glob.glob("sib_inativo_*.csv")

if not arquivos_csv:
    print("ERRO: Nenhum arquivo 'sib_inativo_FF.csv' encontrado.")
    print(f"Arquivos no diretório: {os.listdir('.')}")
else:
    for csv in arquivos_csv:
        processar_sib_trimestral(csv)

print(f"\n[{datetime.now().strftime('%H:%M:%S')}] --- Script Finalizado ---")
