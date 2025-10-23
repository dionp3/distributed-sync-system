import os
import asyncio
from typing import Dict, Any, List
from src.communication.message_passing import NodeCommunication
from src.communication.failure_detector import FailureDetector # Diperlukan untuk Raft/Monitoring

class BaseNode:
    """
    Kelas dasar untuk semua node dalam sistem sinkronisasi terdistribusi.
    Menyediakan inisialisasi dasar, ID node, dan metrik.
    """
    def __init__(self, node_id: str, peers: Dict[str, str], redis_host: str = 'redis'):
        
        # --- Identifikasi & Jaringan ---
        self.node_id = node_id
        self.redis_host = redis_host
        self.peers = peers
        
        # --- Komunikasi ---
        # NodeCommunication digunakan untuk RPC ke peer lain
        self.comm = NodeCommunication(node_id, peers)
        
        # --- Failure Detection ---
        # FailureDetector memantau status peer (berguna untuk Raft)
        peer_ids = [pid for pid in peers.keys() if pid != node_id]
        self.failure_detector = FailureDetector(node_id, peer_ids)
        
        # --- State Dasar & Metrik ---
        self.is_running = False
        self.metrics: Dict[str, Any] = {'node_id': self.node_id, 'uptime': 0.0}
        self.start_time = time.time() # Perlu import time

    def get_metrics(self) -> Dict[str, Any]:
        """Mengembalikan metrik dasar dan menghitung uptime."""
        self.metrics['uptime'] = time.time() - self.start_time
        return self.metrics

    async def start(self):
        """Metode start dasar (akan dioverride oleh subclass)."""
        if self.is_running:
            print(f"Node {self.node_id} sudah berjalan.")
            return

        self.is_running = True
        print(f"BaseNode {self.node_id} memulai.")
        
        # Metode ini akan dikembangkan lebih lanjut di subclass 
        # (misalnya, memulai Raft loop, Redelivery Monitor, dll.)
        
        # Loop monitoring sederhana
        await self._monitor_loop()

    async def _monitor_loop(self):
        """Loop latar belakang untuk pembaruan metrik atau pengecekan dasar."""
        while self.is_running:
            # Perbarui metrik dasar
            self.get_metrics()
            
            # Subclass dapat menambahkan logic pengecekan kesehatan peer di sini
            
            await asyncio.sleep(1) 

    async def stop(self):
        """Menghentikan node dan membersihkan resource."""
        if not self.is_running:
            return

        self.is_running = False
        await self.comm.close()
        print(f"Node {self.node_id} dihentikan.")