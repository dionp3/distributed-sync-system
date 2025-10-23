import os
import asyncio
from typing import Dict, Any, List
from src.communication.message_passing import NodeCommunication
from src.communication.failure_detector import FailureDetector 

class BaseNode:

    def __init__(self, node_id: str, peers: Dict[str, str], redis_host: str = 'redis'):
        
        self.node_id = node_id
        self.redis_host = redis_host
        self.peers = peers
        
        self.comm = NodeCommunication(node_id, peers)
        
        peer_ids = [pid for pid in peers.keys() if pid != node_id]
        self.failure_detector = FailureDetector(node_id, peer_ids)
        
        self.is_running = False
        self.metrics: Dict[str, Any] = {'node_id': self.node_id, 'uptime': 0.0}
        self.start_time = time.time() 

    def get_metrics(self) -> Dict[str, Any]:
        self.metrics['uptime'] = time.time() - self.start_time
        return self.metrics

    async def start(self):
        if self.is_running:
            print(f"Node {self.node_id} sudah berjalan.")
            return

        self.is_running = True
        print(f"BaseNode {self.node_id} memulai.")
        
        await self._monitor_loop()

    async def _monitor_loop(self):
        while self.is_running:
            self.get_metrics()
                        
            await asyncio.sleep(1) 

    async def stop(self):
        if not self.is_running:
            return

        self.is_running = False
        await self.comm.close()
        print(f"Node {self.node_id} dihentikan.")