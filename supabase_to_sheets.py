import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from supabase_sync import get_supabase_client
from upload_to_sheets import upload_csv_to_sheet
from config import SHEET_NAME_MOODLE, SHEET_NAME_ACADEMICO, SHEET_NAME_PARTICIPANTES

def download_supabase_and_upload_to_sheets(table_name: str, sheet_name: str) -> bool:
    print(f"\n[SUPABASE -> SHEETS] 🔄 Iniciando migração da tabela '{table_name}' para a aba '{sheet_name}'.")
    
    client = get_supabase_client()
    if not client:
        print("[SUPABASE -> SHEETS] ❌ Falha ao conectar no Supabase.")
        return False

    try:
        # Fetch all records
        # Note: Supabase limits to 1000 rows by default, we need to paginate or set a higher limit if necessary.
        # But for now, we'll try fetching all. If it fails due to limits, we can paginate.
        print("[SUPABASE -> SHEETS] ⏳ Baixando dados do Supabase (pode demorar alguns segundos)...")
        
        all_data = []
        offset = 0
        limit = 1000
        while True:
            response = client.table(table_name).select("*").range(offset, offset + limit - 1).execute()
            data = response.data
            if not data:
                break
            all_data.extend(data)
            if len(data) < limit:
                break
            offset += limit

        if not all_data:
            print("[SUPABASE -> SHEETS] ℹ️ A tabela está vazia. Nada a sincronizar.")
            return True

        print(f"[SUPABASE -> SHEETS] ✅ {len(all_data)} registros baixados.")

        # Determine headers based on table
        if table_name == "moodle_notas":
            csv_headers = ["Disciplina", "ID_Curso", "Nome_Aluno", "Email", "Nota_Final"]
            db_fields = ["disciplina", "id_curso", "nome_aluno", "email", "nota_final"]
        elif table_name == "moodle_participantes":
            csv_headers = ["Disciplina", "ID_Curso", "Nome_Aluno", "Email", "Papel", "Grupos", "Ultimo_Acesso", "Situacao"]
            db_fields = ["disciplina", "id_curso", "nome_aluno", "email", "papel", "grupos", "ultimo_acesso", "situacao"]
        elif table_name == "academico_notas":
            csv_headers = ["Aluno (CSV)", "Nome (Sistema)", "Codigo", "Disciplina", "Turma", "Media Final", "Situacao", "Observacoes"]
            db_fields = ["aluno_csv", "nome_sistema", "codigo", "disciplina", "turma", "media_final", "situacao", "observacoes"]
        else:
            print(f"[SUPABASE -> SHEETS] ❌ Tabela desconhecida: {table_name}")
            return False

        # Create temp CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_csv_name = f"temp_supabase_{table_name}_{timestamp}.csv"
        temp_csv_path = _BASE_DIR / "CSVs"
        temp_csv_path.mkdir(exist_ok=True)
        temp_csv_file = temp_csv_path / temp_csv_name

        print(f"[SUPABASE -> SHEETS] 📝 Escrevendo arquivo temporário: {temp_csv_name}")
        with open(temp_csv_file, mode="w", newline="", encoding="utf-8-sig") as arquivo_csv:
            data_extracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            escritor_simples = csv.writer(arquivo_csv, delimiter=";")
            escritor_simples.writerow([data_extracao]) 
            
            escritor = csv.writer(arquivo_csv, delimiter=";")
            escritor.writerow(csv_headers)
            
            for row in all_data:
                csv_row = [str(row.get(f, "")) for f in db_fields]
                escritor.writerow(csv_row)

        # Upload
        print("[SUPABASE -> SHEETS] ☁️ Iniciando upload para o Google Sheets...")
        sucesso = upload_csv_to_sheet(temp_csv_file, sheet_name)
        
        # Cleanup
        try:
            os.remove(temp_csv_file)
            print("[SUPABASE -> SHEETS] 🧹 Arquivo temporário removido.")
        except Exception as e:
            print(f"[SUPABASE -> SHEETS] ⚠️ Aviso: Não foi possível remover o arquivo temporário: {e}")

        if sucesso:
            print("[SUPABASE -> SHEETS] ✅ Sincronização completa finalizada com sucesso!")
        return sucesso

    except Exception as e:
        print(f"[SUPABASE -> SHEETS] ❌ Erro durante o processo: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baixa dados do Supabase e envia para o Google Sheets.")
    parser.add_argument("--tabela", required=True, choices=["moodle_notas", "moodle_participantes", "academico_notas"])
    args = parser.parse_args()

    if args.tabela == "moodle_notas":
        download_supabase_and_upload_to_sheets("moodle_notas", SHEET_NAME_MOODLE)
    elif args.tabela == "moodle_participantes":
        download_supabase_and_upload_to_sheets("moodle_participantes", SHEET_NAME_PARTICIPANTES)
    elif args.tabela == "academico_notas":
        download_supabase_and_upload_to_sheets("academico_notas", SHEET_NAME_ACADEMICO)
