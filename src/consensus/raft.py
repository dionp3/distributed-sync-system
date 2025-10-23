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
        self.lock_manager = lock_manager
        self.state = RaftState.FOLLOWER
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[Tuple[int, str]] = []
        self.commit_index = 0
        self.last_applied = 0
        self.leader_id: Optional[str] = None
        
        self.next_index: Dict[str, int] = {p: 1 for p in peers}
        self.match_index: Dict[str, int] = {p: 0 for p in peers}
        
        self.heartbeat_interval = 0.1
        self.election_timeout_min = 1.0
        self.election_timeout_max = 2.5
        self.election_timeout = self._get_random_timeout()
        self.last_contact = time.time()
        self.lock = asyncio.Lock()
        
    def _get_random_timeout(self) -> float:
        return random.uniform(self.election_timeout_min, self.election_timeout_max)
        
    async def start(self):
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
        self.current_term += 1
        self.voted_for = self.node_id
        votes_received = 1
        self.last_contact = time.time()
        
        print(f"Node {self.node_id}: Starting election for term {self.current_term}")

        last_log_index = len(self.log)
        last_log_term = self.log[-1][0] if self.log else 0
        
        payload = {
            'term': self.current_term,
            'candidate_id': self.node_id,
            'last_log_index': last_log_index,
            'last_log_term': last_log_term
        }
        
        results = await self.comm.broadcast_rpc('/raft/request_vote', payload)
        
        for peer_id, result in results.items():
            if not isinstance(result, dict) or result.get('error'):
                continue
                
            if result.get('term', 0) > self.current_term:
                await self._step_down(result['term'])
                return

            if result.get('vote_granted'):
                votes_received += 1
        
        if votes_received >= len(self.peers) // 2 + 1:
            await self._transition_to_leader()
            return
            
        await asyncio.sleep(self.election_timeout)

    async def _leader_loop(self):
        tasks = []
        
        for peer_id in self.peers:
            if peer_id == self.node_id:
                continue
            
            next_idx = self.next_index.get(peer_id, 1)
            prev_log_index = next_idx - 1
            
            prev_log_term = self.log[prev_log_index - 1][0] if prev_log_index > 0 else 0
            
            entries_to_send = self.log[prev_log_index:]
            
            payload = {
                'term': self.current_term,
                'leader_id': self.node_id,
                'prev_log_index': prev_log_index,
                'prev_log_term': prev_log_term,
                'entries': [json.dumps(e) for e in entries_to_send],
                'leader_commit': self.commit_index
            }
            
            tasks.append(self.comm.send_rpc(peer_id, '/raft/append_entries', payload))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, peer_id in enumerate([p for p in self.peers if p != self.node_id]):
            result = results[i]
            if not isinstance(result, dict) or result.get('error'):
                continue
            
            if result.get('term', 0) > self.current_term:
                await self._step_down(result['term'])
                return
            
            if result.get('success'):
                new_match_index = prev_log_index + len(entries_to_send)
                self.match_index[peer_id] = new_match_index
                self.next_index[peer_id] = new_match_index + 1
            else:
                self.next_index[peer_id] = max(1, self.next_index[peer_id] - 1)
        
        await self._check_for_new_commits()
        await asyncio.sleep(self.heartbeat_interval)

    async def _check_for_new_commits(self):
        indices = sorted([self.match_index.get(p, 0) for p in self.peers] + [len(self.log)], reverse=True)
        
        N = indices[len(self.peers) // 2]
        
        if N > self.commit_index and N > 0:
            log_term_at_N = self.log[N - 1][0]
            if log_term_at_N == self.current_term:
                self.commit_index = N
                await self._apply_log()
                print(f"Node {self.node_id} (Leader): Commit Index updated to {self.commit_index}")
    
    async def _apply_log(self):
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            
            log_entry_index = self.last_applied - 1
            if log_entry_index >= len(self.log):
                 break 
                 
            term, command_str = self.log[log_entry_index]
            
            try:
                command = json.loads(command_str)
                self.lock_manager.apply_command(command) 
                
            except json.JSONDecodeError:
                print(f"ERROR: Failed to decode command log at index {self.last_applied}")
            except Exception as e:
                print(f"FATAL STATE MACHINE ERROR at {self.last_applied}: {e}")
                
    def _log_is_at_least_up_to_date(self, candidate_last_index: int, candidate_last_term: int) -> bool:
        last_log_index = len(self.log)
        last_log_term = self.log[-1][0] if self.log else 0
        
        if candidate_last_term != last_log_term:
            return candidate_last_term >= last_log_term
        return candidate_last_index >= last_log_index

    async def _step_down(self, new_term: int):
        self.current_term = new_term
        self.state = RaftState.FOLLOWER
        self.voted_for = None
        self.leader_id = None
        self.last_contact = time.time()
        print(f"Node {self.node_id}: Stepping down to Follower, term {new_term}")
    
    async def handle_request_vote(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self.lock:
            term = payload['term']
            candidate_id = payload['candidate_id']
            
            if term < self.current_term:
                return {'term': self.current_term, 'vote_granted': False}
                
            if term > self.current_term:
                await self._step_down(term) 
                
            log_ok = self._log_is_at_least_up_to_date(payload['last_log_index'], payload['last_log_term'])
            
            if log_ok and (self.voted_for is None or self.voted_for == candidate_id):
                self.voted_for = candidate_id
                self.last_contact = time.time()
                return {'term': self.current_term, 'vote_granted': True}
            else:
                return {'term': self.current_term, 'vote_granted': False}

    async def handle_append_entries(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self.lock:
            term = payload['term']
            leader_id = payload['leader_id']

            if term < self.current_term:
                return {'term': self.current_term, 'success': False}
                
            if term >= self.current_term:
                if term > self.current_term:
                    await self._step_down(term)
                self.state = RaftState.FOLLOWER
                self.leader_id = leader_id
                self.last_contact = time.time()
            
            prev_idx = payload.get('prev_log_index', 0)
            prev_term = payload.get('prev_log_term', 0)
            
            if prev_idx > 0 and (len(self.log) < prev_idx or self.log[prev_idx-1][0] != prev_term):
                return {'term': self.current_term, 'success': False}

            entries_json = payload.get('entries', [])
            if entries_json:
                entries = [json.loads(e) for e in entries_json]
                
                start_index = prev_idx 
                for i, (entry_term, entry_command) in enumerate(entries):
                    idx = start_index + i
                    
                    if idx < len(self.log) and self.log[idx][0] != entry_term:
                        self.log = self.log[:idx]
                        self.log.append((entry_term, entry_command))
                    elif idx >= len(self.log):
                        self.log.append((entry_term, entry_command))
            
            leader_commit = payload['leader_commit']
            if leader_commit > self.commit_index:
                new_commit_index = min(leader_commit, len(self.log))
                if new_commit_index > self.commit_index:
                    self.commit_index = new_commit_index
                    await self._apply_log() 

            return {'term': self.current_term, 'success': True}

    async def _transition_to_leader(self):
        self.state = RaftState.LEADER
        self.leader_id = self.node_id
        self.next_index = {p: len(self.log) + 1 for p in self.peers}
        self.match_index = {p: len(self.log) for p in self.peers}
        print(f"Node {self.node_id}: Received majority votes. Becoming Leader.")
        await self._leader_loop()
        
    def submit_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if self.state != RaftState.LEADER:
            return (False, self.leader_id)
        
        log_entry = (self.current_term, json.dumps(command))
        self.log.append(log_entry)
        
        return (True, None)