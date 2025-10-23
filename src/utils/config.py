import os
import json
from typing import Dict, Any, List


def get_peers(env_var: str) -> Dict[str, str]:
    val = os.getenv(env_var)
    if not val:
        return {} 
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        print(f"ERROR: Failed to decode JSON for {env_var}. Check .env file format.")
        return {}

def get_node_list(env_var: str) -> List[str]:
    val = os.getenv(env_var)
    if not val:
        return []
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        print(f"ERROR: Failed to decode JSON list for {env_var}.")
        return []

def get_cache_max_size(default: int = 100) -> int:
    size_str = os.getenv("CACHE_MAX_SIZE")
    if size_str and size_str.isdigit():
        return int(size_str)
    return default


CONFIG = {
    "REDIS_HOST": os.getenv("REDIS_HOST", "redis"),
    "RAFT_PEERS": get_peers("RAFT_PEERS"),
    "CACHE_PEERS": get_peers("CACHE_PEERS"),
    "QUEUE_NODES": get_node_list("QUEUE_NODES"),
    "CACHE_MAX_SIZE": get_cache_max_size()
}