import time
import json
import asyncio
from typing import Dict, Any, Optional
from src.consensus.raft import RaftNode, RaftState

class DistributedLockManager:
    """State Machine untuk Raft, mengelola Lock Table."""
    def __init__(self, raft_node: RaftNode):
        self.raft_node = raft_node
        # Lock Table: {lock_name: {type: str, holders: List[str], expiry: float, queue: List[Dict]}}
        self.locks: Dict[str, Dict] = {} 
        self.waiting_clients: Dict[str, asyncio.Event] = {} # {client_id: Event}

    def is_leader(self):
        return self.raft_node.state == RaftState.LEADER

    async def acquire_lock(self, lock_name: str, lock_type: str, client_id: str, timeout: float = 10.0):
        """
        Klien API: Mengirim permintaan lock ke Leader.
        """
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

        # Tunggu hingga command di-commit dan diterapkan ke State Machine
        self.waiting_clients[client_id] = asyncio.Event()
        try:
            # Tunggu Event di-set oleh apply_command atau timeout
            await asyncio.wait_for(self.waiting_clients[client_id].wait(), timeout=timeout + 2) 
            
            # Cek status lock setelah diterapkan
            if self.locks.get(lock_name) and client_id in self.locks[lock_name]['holders']:
                return {"success": True, "message": f"{lock_type} lock acquired"}
            else:
                return {"success": False, "error": "LOCK_DENIED_OR_TIMEOUT"}
        except asyncio.TimeoutError:
            return {"success": False, "error": "LOCK_TIMEOUT"}
        finally:
            self.waiting_clients.pop(client_id, None)

    async def release_lock(self, lock_name: str, client_id: str):
        """Klien API: Melepaskan lock."""
        if not self.is_leader():
            return {"success": False, "error": "NOT_LEADER", "leader_hint": self.raft_node.leader_id}
            
        command = {"type": "RELEASE", "lock_name": lock_name, "client_id": client_id}
        success, leader_hint = self.raft_node.submit_command(command)
        
        # Di sini, kita tidak perlu menunggu Event. Cukup tunggu replikasi (simulasi)
        await asyncio.sleep(0.1) 
        
        return {"success": success, "message": "Release command submitted"}

    def apply_command(self, command: Dict[str, Any]):
        """DIPANGGIL oleh RaftNode._apply_log() setelah commit."""
        lock_name = command['lock_name']
        client_id = command['client_id']
        lock_type = command.get('lock_type', 'exclusive')

        if command['type'] == 'ACQUIRE':
            current_lock = self.locks.get(lock_name)
            granted = False
            
            if not current_lock:
                # Lock pertama kali: Selalu granted
                granted = True
            elif current_lock['type'] == 'shared' and lock_type == 'shared':
                # Shared Lock di Shared Lock: Granted
                granted = True
            elif current_lock['type'] == 'shared' and lock_type == 'exclusive':
                # Shared Lock di Exclusive Lock: Denied (kecuali holders kosong)
                granted = False
            elif current_lock['type'] == 'exclusive':
                # Exclusive Lock di Lock apapun: Denied
                granted = False
            
            if granted:
                if not current_lock:
                    self.locks[lock_name] = {'type': lock_type, 'holders': [client_id], 'expiry': command['expiry']}
                else:
                    self.locks[lock_name]['holders'].append(client_id)
                
                # Set Event untuk klien yang menunggu (jika ada)
                event = self.waiting_clients.get(client_id)
                if event: event.set()
                return True
            else:
                # Tambahkan ke antrian menunggu (jika implementasi lebih kompleks)
                return False

        elif command['type'] == 'RELEASE':
            if lock_name in self.locks and client_id in self.locks[lock_name]['holders']:
                 self.locks[lock_name]['holders'].remove(client_id)
                 if not self.locks[lock_name]['holders']:
                     del self.locks[lock_name]
                     # Notifikasi antrian menunggu (jika ada)
                 return True
            return False

    async def deadlock_monitor(self):
        """Implementasi Deadlock Detection (Timeout-Based) - Hanya di Leader."""
        while True:
            if self.is_leader():
                now = time.time()
                for name, lock_data in list(self.locks.items()): # Gunakan list() untuk iterasi aman
                    if lock_data['expiry'] < now:
                        # Lock Expired: Paksa rilis (Deadlock Detection)
                        print(f"DEADLOCK DETECTED: Lock {name} expired. Force releasing.")
                        
                        # Buat command RELEASE otomatis melalui Raft Log
                        release_cmd = {"type": "RELEASE", "lock_name": name, "client_id": "SYSTEM_TIMEOUT"}
                        self.raft_node.submit_command(release_cmd) # Rilis secara asinkron
            
            await asyncio.sleep(5)