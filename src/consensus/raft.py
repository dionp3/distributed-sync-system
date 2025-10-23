import random
import time
import json
import asyncio
from enum import Enum
from typing import List, Dict, Tuple, Optional, Any
from src.communication.message_passing import NodeCommunication

class RaftState(Enum):
    FOLLOWER = 'follower'
    CANDIDATE = 'candidate'
    LEADER = 'leader'

class RaftNode:
    def __init__(self, node_id: str, peers: List[str], comm: NodeCommunication, lock_manager):
        self.node_id = node_id
        self.peers = peers
        self.comm = comm
        self.lock_manager = lock_manager # Referensi ke State Machine
        self.state = RaftState.FOLLOWER
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[Tuple[int, str]] = [] # (term, command_json_str)
        self.commit_index = 0
        self.last_applied = 0
        self.leader_id: Optional[str] = None
        
        # Leader Volatile State
        self.next_index: Dict[str, int] = {p: 1 for p in peers}
        self.match_index: Dict[str, int] = {p: 0 for p in peers}
        
        self.heartbeat_interval = 0.1
        self.election_timeout_min = 1.0
        self.election_timeout_max = 2.5
        self.election_timeout = self._get_random_timeout()
        self.last_contact = time.time()
        self.lock = asyncio.Lock()
        
    # --- Raft Core Logic (Disederhanakan untuk brevity, fokus pada alur) ---

    def _get_random_timeout(self) -> float:
        return random.uniform(self.election_timeout_min, self.election_timeout_max)
        
    async def start(self):
        """Memulai loop utama Raft."""
        while True:
            if self.state == RaftState.FOLLOWER and time.time() - self.last_contact > self.election_timeout:
                await self._transition_to_candidate()
            elif self.state == RaftState.CANDIDATE:
                await self._run_election()
            elif self.state == RaftState.LEADER:
                await self._leader_loop()
            
            await asyncio.sleep(self.heartbeat_interval / 2)

    async def _transition_to_candidate(self):
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.last_contact = time.time()
        self.election_timeout = self._get_random_timeout()
        self.leader_id = None
        print(f"Node {self.node_id}: Starting election for term {self.current_term}")

    async def _run_election(self):
        # ... Logika mengirim RequestVote RPC dan menghitung suara (Sama seperti kerangka sebelumnya) ...
        # Jika menang:
        # self.state = RaftState.LEADER
        # self._initialize_leader_state()
        pass

    async def _leader_loop(self):
        """Logika Heartbeat dan Replikasi Log."""
        # ... (Sama seperti logika Leader yang ditingkatkan di jawaban sebelumnya) ...
        await self._check_for_new_commits()
        await asyncio.sleep(self.heartbeat_interval)

    async def _check_for_new_commits(self):
        """Mengecek jika ada log yang bisa dicommit ke State Machine."""
        
        # Cari N tertinggi (index log) yang sudah direplikasi di mayoritas (N/2 + 1)
        # N harus berasal dari current_term Leader
        # ... (Logika sama seperti jawaban sebelumnya) ...

        # Jika ditemukan N yang baru:
        # self.commit_index = N
        # await self._apply_log()
        pass
    
    # --- State Machine Integration ---
    async def _apply_log(self):
        """Menerapkan command baru ke State Machine (Lock Manager)."""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            term, command_str = self.log[self.last_applied - 1]
            try:
                command = json.loads(command_str)
                # Panggil logika apply_command pada Lock Manager
                self.lock_manager.apply_command(command) 
                # (Di Lock Manager, pastikan logika menunggu hasilnya)
            except Exception as e:
                print(f"Error applying command: {e}")
                
    # --- RPC Handlers ---
    # Implementasikan handle_request_vote dan handle_append_entries sepenuhnya
    # Pastikan untuk mereset last_contact dan mengubah state menjadi FOLLOWER jika term Leader lebih tinggi.
    # ...
    
    def submit_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """API internal untuk klien, hanya Leader yang boleh menerima command."""
        if self.state != RaftState.LEADER:
            return (False, self.leader_id)
        
        log_entry = (self.current_term, json.dumps(command))
        self.log.append(log_entry)
        
        # Note: Replikasi akan terjadi di loop berikutnya. 
        # API klien harus menunggu hingga log_entry ini di-commit dan diterapkan.
        return (True, None)