import time
import json
import asyncio
import uuid
from typing import Dict, Any, Optional, List

from src.consensus.raft import RaftNode, RaftState

class DistributedLockManager:
    def __init__(self, raft_node: Optional[RaftNode]):
        self.raft_node = raft_node
        self.locks: Dict[str, Dict] = {} 
        self.waiting_clients: Dict[str, asyncio.Event] = {}

    def is_leader(self):
        return self.raft_node is not None and self.raft_node.state == RaftState.LEADER

    async def acquire_lock(self, lock_name: str, lock_type: str, client_id: str, timeout: float = 10.0):
        if not self.is_leader():
            return {"success": False, "error": "NOT_LEADER", "leader_hint": self.raft_node.leader_id}
        
        command = {
            "type": "ACQUIRE",
            "lock_name": lock_name,
            "lock_type": lock_type,
            "client_id": client_id,
            "expiry": time.time() + timeout
        }

        success, leader_hint = self.raft_node.submit_command(command)
        if not success:
            return {"success": False, "error": "SUBMIT_FAILED", "leader_hint": leader_hint}

        self.waiting_clients[client_id] = asyncio.Event()
        try:
            await asyncio.wait_for(self.waiting_clients[client_id].wait(), timeout=timeout + 0.5) 
            
            if self.locks.get(lock_name) and client_id in self.locks[lock_name]['holders']:
                return {"success": True, "message": f"{lock_type} lock acquired"}
            else:
                return {"success": False, "error": "LOCK_DENIED_OR_TIMEOUT"}
        except asyncio.TimeoutError:
            return {"success": False, "error": "LOCK_TIMEOUT"}
        finally:
            self.waiting_clients.pop(client_id, None)

    async def release_lock(self, lock_name: str, client_id: str):
        if not self.is_leader():
            return {"success": False, "error": "NOT_LEADER", "leader_hint": self.raft_node.leader_id}
            
        command = {"type": "RELEASE", "lock_name": lock_name, "client_id": client_id}
        success, leader_hint = self.raft_node.submit_command(command)
        
        return {"success": success, "message": "Release command submitted"}

    def apply_command(self, command: Dict[str, Any]):
        lock_name = command['lock_name']
        client_id = command.get('client_id', 'SYSTEM_TIMEOUT')
        lock_type = command.get('lock_type', 'exclusive')

        granted = False
        if command['type'] == 'ACQUIRE':
            current_lock = self.locks.get(lock_name)
            
            if not current_lock:
                granted = True
            elif current_lock['type'] == 'shared' and lock_type == 'shared':
                granted = True
            
            if granted:
                if not current_lock:
                    self.locks[lock_name] = {'type': lock_type, 'holders': [client_id], 'expiry': command['expiry']}
                else:
                    self.locks[lock_name]['holders'].append(client_id)
                
                event = self.waiting_clients.get(client_id)
                if event: event.set()
                return True

        elif command['type'] == 'RELEASE':
            if lock_name in self.locks:
                 current_lock = self.locks[lock_name]
                 
                 if client_id == 'SYSTEM_TIMEOUT':
                      del self.locks[lock_name]
                      # print(f"System Force Release Succeeded for {lock_name}")
                      return True

                 elif client_id in current_lock['holders']:
                      current_lock['holders'].remove(client_id)
                      if not current_lock['holders']:
                         del self.locks[lock_name]
                         return True
            return False
            
    async def deadlock_monitor(self):
        while True:
            if self.raft_node and self.is_leader():
                now = time.time()
                
                for name, lock_data in list(self.locks.items()):
                    if lock_data.get('expiry', 0) < now: 
                        release_cmd = {"type": "RELEASE", "lock_name": name, "client_id": "SYSTEM_TIMEOUT"}
                        self.raft_node.submit_command(release_cmd) 
                        # print(f"DEADLOCK DETECTED: Lock {name} expired. Force releasing.")
                        
            await asyncio.sleep(0.5)