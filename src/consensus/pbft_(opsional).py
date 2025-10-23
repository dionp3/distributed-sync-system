import asyncio
import json
from typing import List, Dict, Any, Optional
from src.communication.message_passing import NodeCommunication

PBFT_THRESHOLD = lambda N: (N * 2) // 3 + 1 
TIMEOUT_SECS = 5 

class PBFTState:
    def __init__(self, N: int):
        self.sequence_number = 0
        self.view_number = 0
        self.message_log: Dict[int, Dict[str, Any]] = {} 
        self.prepared: Dict[int, bool] = {} 
        self.committed: Dict[int, bool] = {} 
        self.total_nodes = N
        self.quorum_size = PBFT_THRESHOLD(N)
        self.primary_id = None 

class PBFTNode:
    def __init__(self, node_id: str, peers: List[str], comm: NodeCommunication):
        self.node_id = node_id
        self.peers = peers
        self.comm = comm
        self.state = PBFTState(len(peers) + 1)
        
        self.state.primary_id = sorted([self.node_id] + self.peers)[0] 
        self.is_primary = (self.node_id == self.state.primary_id)
        self.lock = asyncio.Lock()
        
    async def start(self):
        if self.is_primary:
            print(f"PBFT Node {self.node_id} starting as PRIMARY.")
        else:
            print(f"PBFT Node {self.node_id} starting as REPLICA.")
        
        while True:
             await asyncio.sleep(1) 

    def _get_message_key(self, seq_num: int, phase: str, node_id: str) -> str:
        return f"{seq_num}-{phase}-{node_id}"

    # --- Klien API: Submit Command ---
    async def submit_client_request(self, command: Dict[str, Any]):
        if not self.is_primary:
            return {"success": False, "error": "NOT_PRIMARY", "primary": self.state.primary_id}
            
        async with self.lock:
            self.state.sequence_number += 1
            seq_num = self.state.sequence_number
            
            print(f"PBFT Primary {self.node_id}: Starting consensus for seq={seq_num}")

            await self._send_pre_prepare(seq_num, command)
            
            return {"success": True, "message": f"Consensus started for seq={seq_num}"}

    async def _send_pre_prepare(self, seq_num: int, command: Dict[str, Any]):
        payload = {
            "type": "PRE-PREPARE",
            "view": self.state.view_number,
            "seq": seq_num,
            "digest": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
            "sender": self.node_id,
            "command": command
        }
        
        self.state.message_log[seq_num] = {"PRE-PREPARE": {self.node_id: payload}}

        await self.comm.broadcast_rpc('/pbft/message', payload)

    async def handle_pre_prepare(self, payload: Dict[str, Any]):
        seq_num = payload['seq']
                
        async with self.lock:
            if seq_num not in self.state.message_log:
                self.state.message_log[seq_num] = {}
            if "PRE-PREPARE" not in self.state.message_log[seq_num]:
                 self.state.message_log[seq_num]["PRE-PREPARE"] = {}
            self.state.message_log[seq_num]["PRE-PREPARE"][payload['sender']] = payload

            print(f"PBFT Replica {self.node_id}: Received PRE-PREPARE for seq={seq_num}. Sending PREPARE.")
            
            await self._send_prepare(seq_num, payload['digest'])
            
    async def _send_prepare(self, seq_num: int, digest: str):
        payload = {
            "type": "PREPARE",
            "view": self.state.view_number,
            "seq": seq_num,
            "digest": digest,
            "sender": self.node_id
        }
        await self.comm.broadcast_rpc('/pbft/message', payload)

    async def handle_prepare(self, payload: Dict[str, Any]):
        seq_num = payload['seq']
        sender = payload['sender']
        
        async with self.lock:
            if seq_num not in self.state.message_log:
                self.state.message_log[seq_num] = {}
            if "PREPARE" not in self.state.message_log[seq_num]:
                 self.state.message_log[seq_num]["PREPARE"] = {}
            self.state.message_log[seq_num]["PREPARE"][sender] = payload
            
            if not self.state.prepared.get(seq_num):
                prepare_count = len(self.state.message_log[seq_num].get("PREPARE", {}))
                
                if prepare_count >= self.state.quorum_size:
                    self.state.prepared[seq_num] = True
                    print(f"PBFT Node {self.node_id}: Prepared for seq={seq_num}. Sending COMMIT.")
                    
                    await self._send_commit(seq_num, payload['digest'])

    # FASE 3: COMMIT (Replica)
    async def _send_commit(self, seq_num: int, digest: str):
        payload = {
            "type": "COMMIT",
            "view": self.state.view_number,
            "seq": seq_num,
            "digest": digest,
            "sender": self.node_id
        }
        await self.comm.broadcast_rpc('/pbft/message', payload)

    async def handle_commit(self, payload: Dict[str, Any]):
        seq_num = payload['seq']
        sender = payload['sender']
        
        async with self.lock:
            if seq_num not in self.state.message_log:
                self.state.message_log[seq_num] = {}
            if "COMMIT" not in self.state.message_log[seq_num]:
                 self.state.message_log[seq_num]["COMMIT"] = {}
            self.state.message_log[seq_num]["COMMIT"][sender] = payload
            
            if not self.state.committed.get(seq_num):
                commit_count = len(self.state.message_log[seq_num].get("COMMIT", {}))
                
                if commit_count >= self.state.quorum_size:
                    self.state.committed[seq_num] = True
                    print(f"PBFT Node {self.node_id}: Committed for seq={seq_num}. Applying command.")
                    
                    await self._apply_command(seq_num)

    async def _apply_command(self, seq_num: int):
        print(f"PBFT Node {self.node_id}: SUCCESSFULLY EXECUTED command for seq={seq_num}")