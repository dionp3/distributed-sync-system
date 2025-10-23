import os
import json
from typing import Dict, Any, List

# --- CONFIGURATIONS DARI .ENV ---

def get_peers(env_var: str) -> Dict[str, str]:
    """Mengambil dan mengurai variabel lingkungan JSON untuk daftar peer (misalnya RAFT_PEERS, CACHE_PEERS)."""
    val = os.getenv(env_var)
    if not val:
        # Nilai default harus didefinisikan secara eksplisit di .env, 
        # tetapi ini adalah safety fallback jika .env gagal dimuat.
        return {} 
    try:
        # Mengembalikan dictionary of {'node_id': 'http://host:port'}
        return json.loads(val)
    except json.JSONDecodeError:
        print(f"ERROR: Failed to decode JSON for {env_var}. Check .env file format.")
        return {}

def get_node_list(env_var: str) -> List[str]:
    """Mengambil dan mengurai variabel lingkungan JSON untuk daftar node (misalnya QUEUE_NODES)."""
    val = os.getenv(env_var)
    if not val:
        return []
    try:
        # Mengembalikan list of ['node1', 'node2', ...]
        return json.loads(val)
    except json.JSONDecodeError:
        print(f"ERROR: Failed to decode JSON list for {env_var}.")
        return []

def get_cache_max_size(default: int = 100) -> int:
    """Mengambil ukuran maksimum cache dari environment."""
    size_str = os.getenv("CACHE_MAX_SIZE")
    if size_str and size_str.isdigit():
        return int(size_str)
    return default

# --- EXPORT CONFIGURATION ---

# Objek konfigurasi yang dapat diakses oleh semua modul
CONFIG = {
    "REDIS_HOST": os.getenv("REDIS_HOST", "redis"),
    "RAFT_PEERS": get_peers("RAFT_PEERS"),
    "CACHE_PEERS": get_peers("CACHE_PEERS"),
    "QUEUE_NODES": get_node_list("QUEUE_NODES"),
    "CACHE_MAX_SIZE": get_cache_max_size()
}