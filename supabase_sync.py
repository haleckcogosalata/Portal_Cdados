import sys
from pathlib import Path
from typing import List, Dict, Any

# Ensure config.py can be found
_BASE_DIR = Path(__file__).resolve().parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

try:
    from config import SUPABASE_URL, SUPABASE_KEY
except ImportError:
    SUPABASE_URL = None
    SUPABASE_KEY = None

def get_supabase_client():
    try:
        from supabase import create_client, Client
        if SUPABASE_URL and SUPABASE_KEY:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
    except ImportError:
        print("[SUPABASE] ⚠️ Biblioteca 'supabase' não está instalada. Execute: pip install -r requirements.txt")
    except Exception as e:
        print(f"[SUPABASE] ❌ Erro ao criar cliente Supabase: {e}")
    return None

def sync_to_supabase(table_name: str, data: List[Dict[str, Any]], delete_by_col: str = None) -> bool:
    """
    Sincroniza os dados extraídos com o Supabase.
    - Converte chaves do dicionário para lowercase e substitui espaços/parênteses para bater com as tabelas SQL.
    - Se delete_by_col for passado, acha todos os valores únicos dessa coluna nos dados e deleta no Supabase antes de inserir.
    """
    if not data:
        print(f"[SUPABASE] ℹ️ Nenhum dado para sincronizar na tabela {table_name}.")
        return True

    client = get_supabase_client()
    if not client:
        return False

    # 1. Transformar chaves para formato SQL (lowercase, sem espaços, sem parênteses)
    formatted_data = []
    for row in data:
        new_row = {}
        for k, v in row.items():
            new_key = k.lower().replace(" (csv)", "_csv").replace(" (sistema)", "_sistema").replace(" ", "_")
            new_row[new_key] = v
        formatted_data.append(new_row)

    print(f"[SUPABASE] 🔄 Iniciando sincronização para tabela '{table_name}' ({len(formatted_data)} registros)...")

    try:
        # 2. Se especificado delete_by_col, apagar os registros antigos das disciplinas/cursos atualizados
        if delete_by_col:
            # Pegar valores únicos
            unique_values = set(str(row.get(delete_by_col)) for row in formatted_data if row.get(delete_by_col))
            if unique_values:
                print(f"[SUPABASE] 🗑️ Apagando dados antigos baseados em '{delete_by_col}' = {unique_values}")
                for val in unique_values:
                    # Deletar linha a linha por segurança/limitação de in ou eq com listas
                    client.table(table_name).delete().eq(delete_by_col, val).execute()

        # 3. Inserir os novos dados em blocos (chunking) para não dar timeout
        chunk_size = 500
        for i in range(0, len(formatted_data), chunk_size):
            chunk = formatted_data[i:i + chunk_size]
            client.table(table_name).insert(chunk).execute()
        
        print(f"[SUPABASE] ✅ Sincronização concluída com sucesso para '{table_name}'.")
        return True

    except Exception as e:
        print(f"[SUPABASE] ❌ Erro na sincronização com Supabase: {e}")
        return False

def get_distinct_from_supabase(table_name: str, column_name: str) -> list[str]:
    """
    Busca os valores distintos de uma coluna no Supabase usando paginação
    para contornar o limite de 1000 linhas padrão.
    """
    client = get_supabase_client()
    if not client:
        return []
    try:
        all_data = []
        limit = 1000
        offset = 0
        
        while True:
            response = client.table(table_name).select(column_name).range(offset, offset + limit - 1).execute()
            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < limit:
                break
            offset += limit

        if all_data:
            unique_vals = list(set(str(row[column_name]) for row in all_data if row.get(column_name)))
            return sorted(unique_vals)
        return []
    except Exception as e:
        print(f"[SUPABASE] ❌ Erro ao buscar {column_name} da tabela {table_name}: {e}")
        return []

def get_name_adjustments() -> dict[str, str]:
    """
    Busca os ajustes de nomes da tabela 'ajuste_nomes' no Supabase.
    Retorna um dicionário {nome_moodle: nome_academico}.
    """
    client = get_supabase_client()
    if not client:
        return {}
    
    try:
        all_data = []
        limit = 1000
        offset = 0
        
        while True:
            response = client.table("ajuste_nomes").select("*").range(offset, offset + limit - 1).execute()
            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < limit:
                break
            offset += limit
            
        return {row["nome_moodle"]: row["nome_academico"] for row in all_data if row.get("nome_moodle") and row.get("nome_academico")}
    except Exception as e:
        print(f"[SUPABASE] ❌ Erro ao buscar ajustes de nomes: {e}")
        return {}

def save_name_adjustment(nome_moodle: str, nome_academico: str) -> bool:
    """
    Insere ou atualiza um ajuste de nome no Supabase.
    """
    client = get_supabase_client()
    if not client:
        return False
    
    try:
        data = {"nome_moodle": nome_moodle.strip(), "nome_academico": nome_academico.strip()}
        client.table("ajuste_nomes").upsert(data).execute()
        return True
    except Exception as e:
        print(f"[SUPABASE] ❌ Erro ao salvar ajuste de nome '{nome_moodle}': {e}")
        return False

def delete_name_adjustment(nome_moodle: str) -> bool:
    """
    Remove um ajuste de nome do Supabase.
    """
    client = get_supabase_client()
    if not client:
        return False
    
    try:
        client.table("ajuste_nomes").delete().eq("nome_moodle", nome_moodle.strip()).execute()
        return True
    except Exception as e:
        print(f"[SUPABASE] ❌ Erro ao deletar ajuste de nome '{nome_moodle}': {e}")
        return False

def get_all_moodle_names() -> set[str]:
    """
    Retorna a união de todos os nomes de alunos presentes nas tabelas do Moodle.
    """
    n1 = get_distinct_from_supabase("moodle_notas", "nome_aluno")
    n2 = get_distinct_from_supabase("moodle_participantes", "nome_aluno")
    return set(n1 + n2)
