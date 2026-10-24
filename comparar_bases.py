import sys
import csv
from pathlib import Path
from supabase_sync import get_supabase_client

BASE_DIR = Path(__file__).resolve().parent

def fetch_all(client, table_name, column_name):
    all_data = []
    offset = 0
    limit = 1000
    while True:
        res = client.table(table_name).select(column_name).range(offset, offset + limit - 1).execute()
        if not res.data:
            break
        all_data.extend(res.data)
        if len(res.data) < limit:
            break
        offset += limit
    return all_data

def comparar_moodle_academico():
    client = get_supabase_client()
    if not client:
        print("[ERRO] Não foi possível conectar ao Supabase.")
        return

    print("[INFO] Buscando dados no Supabase (ignorando limite de 1000 linhas)...")
    
    # Busca alunos do Moodle e guarda a data de extração mais recente
    data_moodle = fetch_all(client, "moodle_notas", "nome_aluno, data_extracao")
    alunos_moodle_dict = {}  # {NOME_UPPER: (nome_original, max_data)}
    for row in data_moodle:
        nome = row.get("nome_aluno")
        data_ext = row.get("data_extracao") or ""
        if nome:
            nome_upper = nome.strip().upper()
            if nome_upper not in alunos_moodle_dict or data_ext > alunos_moodle_dict[nome_upper][1]:
                alunos_moodle_dict[nome_upper] = (nome.strip(), data_ext)
    
    # Busca alunos do Acadêmico e guarda a data de extração mais recente
    data_acad = fetch_all(client, "academico_notas", "aluno_csv, nome_sistema, data_extracao")
    alunos_acad_dict = {} # {NOME_UPPER: max_data}
    for row in data_acad:
        data_ext = row.get("data_extracao") or ""
        
        nome_sis = row.get("nome_sistema")
        if nome_sis:
            ns_upper = nome_sis.strip().upper()
            if ns_upper not in alunos_acad_dict or data_ext > alunos_acad_dict[ns_upper]:
                alunos_acad_dict[ns_upper] = data_ext
                
        aluno_csv = row.get("aluno_csv")
        if aluno_csv:
            ac_upper = aluno_csv.strip().upper()
            if ac_upper not in alunos_acad_dict or data_ext > alunos_acad_dict[ac_upper]:
                alunos_acad_dict[ac_upper] = data_ext
    
    faltantes = []
    outdated_count = 0
    for nome_upper, (nome_original, data_moodle_ext) in alunos_moodle_dict.items():
        if nome_upper not in alunos_acad_dict:
            faltantes.append(nome_original)
        else:
            # Compara as datas: se a extração do Moodle for mais recente que a do Acadêmico
            data_acad_ext = alunos_acad_dict[nome_upper]
            if data_moodle_ext > data_acad_ext:
                faltantes.append(nome_original)
                outdated_count += 1

    faltantes = sorted(faltantes)
    
    if not faltantes:
        print("[OK] Todos os alunos do Moodle estão atualizados no Acadêmico!")
        return

    print(f"[AVISO] Foram encontrados {len(faltantes)} alunos pendentes (Novos ou Desatualizados no Acadêmico):")
    if outdated_count > 0:
        print(f"        -> {outdated_count} desses já existiam mas precisam ser atualizados pois o Moodle é mais recente.")
    for aluno in faltantes:
        print(f"  - {aluno}")
        
    # Gera o CSV para reprocessamento
    pasta_csv = Path(BASE_DIR) / "Acadêmico" / "CSVs"
    pasta_csv.mkdir(parents=True, exist_ok=True)
    caminho_csv = pasta_csv / "faltantes_moodle_academico.csv"
    
    try:
        with open(caminho_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Curso", "ID", "Nome", "Email"])
            writer.writerow(["", "", "", ""]) # Pula a segunda linha, igual ao CSV original do Moodle
            for i, aluno in enumerate(faltantes):
                writer.writerow(["Curso Faltante", "", aluno, f"email_{i}@faltante.com"])
        print(f"\n[OK] CSV para reprocessamento gerado em: {caminho_csv.name}")
    except Exception as e:
        print(f"[ERRO] Falha ao gerar CSV de faltantes: {e}")

if __name__ == "__main__":
    comparar_moodle_academico()
