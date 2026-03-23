import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("WARNING: SUPABASE_URL or SUPABASE_KEY not set in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def save_state(state: str):
    if not supabase: return
    supabase.table("states").insert({"state": state}).execute()

def verify_and_delete_state(state: str) -> bool:
    if not supabase: return False
    response = supabase.table("states").select("state").eq("state", state).execute()
    if response.data:
        supabase.table("states").delete().eq("state", state).execute()
        return True
    return False

def save_tokens(access_token: str, refresh_token: str):
    if not supabase: return
    # Assuming one row for now, or you can map to a user_id
    # Try to update the first row, if not exists, insert
    existing = supabase.table("tokens").select("id").limit(1).execute()
    if existing.data:
        supabase.table("tokens").update({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "updated_at": "now()"
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table("tokens").insert({
            "access_token": access_token,
            "refresh_token": refresh_token
        }).execute()

def get_tokens():
    if not supabase: return None
    response = supabase.table("tokens").select("*").limit(1).execute()
    return response.data[0] if response.data else None