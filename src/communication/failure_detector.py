import asyncio
import time
from typing import Dict, Any, List

class FailureDetector:
    def __init__(self, node_id: str, peer_ids: List[str], election_timeout: float = 2.0):
        self.node_id = node_id
        self.peer_ids = peer_ids
        self.election_timeout = election_timeout
        self.last_seen: Dict[str, float] = {pid: time.time() for pid in peer_ids}
        self.is_leader_active = True
        self.leader_id: Optional[str] = None

    def record_heartbeat(self, sender_id: str):
        if sender_id in self.peer_ids or sender_id == self.node_id:
            self.last_seen[sender_id] = time.time()

    def set_leader(self, leader_id: str):
        self.leader_id = leader_id
        self.is_leader_active = True
        self.record_heartbeat(leader_id)

    def check_leader_failure(self, current_leader_id: Optional[str]) -> bool:
        if not current_leader_id:
            return False 

        last_contact_time = self.last_seen.get(current_leader_id, 0)
        
        if (time.time() - last_contact_time) > self.election_timeout:
            if self.is_leader_active:
                print(f"[{self.node_id}] LEADER FAILURE DETECTED: {current_leader_id} timeout.")
                self.is_leader_active = False 
            return True
        
        return False

    def get_time_since_last_contact(self, peer_id: str) -> float:
        last_contact = self.last_seen.get(peer_id, 0)
        if last_contact == 0:
            return float('inf')
        return time.time() - last_contact