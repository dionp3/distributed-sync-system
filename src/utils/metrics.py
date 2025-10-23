# FILE: src/utils/metrics.py

from typing import Dict, Any

def format_prometheus_metrics(metrics_dict: Dict[str, Any]) -> str:
    output = "# HELP distributed_sync_metrics Metrics reported by the node.\n"
    output += "# TYPE distributed_sync_metrics gauge\n"
    
    labeled_metrics = {}
    
    for key, value in metrics_dict.items():
        if key in ('node_id', 'state', 'status', 'is_leader'):
            labeled_metrics[key] = str(value)
            continue
        
        if isinstance(value, (int, float)):
            output += f"{key} {value}\n"
        
    node_id = labeled_metrics.get("node_id", "unknown")

    if 'state' in labeled_metrics:
        output += f'raft_state_info{{node_id="{node_id}", raft_state="{labeled_metrics["state"]}"}} 1\n'
    if 'is_leader' in labeled_metrics:
        is_leader_value = 1 if labeled_metrics["is_leader"].lower() == "true" else 0
        output += f'raft_is_leader {is_leader_value}\n'
        
    if 'status' in labeled_metrics:
        output += f'queue_node_status{{node_id="{node_id}", node_status="{labeled_metrics["status"]}"}} 1\n'
        
    if 'hits' in metrics_dict and 'misses' in metrics_dict:
        hits = metrics_dict.get('hits', 0)
        misses = metrics_dict.get('misses', 0)
        total = hits + misses
        hit_ratio = hits / total if total > 0 else 0
        output += f"cache_hit_ratio {hit_ratio}\n"
        
    return output.strip()