import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from supabase_sync import get_supabase_client

client = get_supabase_client()
if client:
    res = client.table("moodle_notas").select("*").limit(1).execute()
    print("moodle_notas columns:", res.data[0].keys() if res.data else "empty")
    
    res2 = client.table("moodle_participantes").select("*").limit(1).execute()
    print("moodle_participantes columns:", res2.data[0].keys() if res2.data else "empty")
else:
    print("Failed to get client.")
