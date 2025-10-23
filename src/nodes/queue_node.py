import redis
import json
import time
import hashlib
import bisect
from typing import List, Dict, Any, Optional

# --- Consistent Hashing Implementation ---

VIRTUAL_NODES = 100 
HASH_SPACE = 2**32

class ConsistentHashRing:
    """Mengelola pemetaan Topic ke Queue Nodes secara konsisten."""
    def __init__(self, nodes: List[str]):
        # nodes: Daftar ID node (e.g., ['node_queue_1', 'node_queue_2', ...])
        self.nodes = nodes
        self.ring: Dict[int, str] = {} # {hash_value: node_id}
        self.sorted_keys: List[int] = []
        if nodes:
            self._build_ring()

    def _build_ring(self):
        """Membangun hash ring dengan virtual nodes."""
        self.ring.clear()
        for node in self.nodes:
            for i in range(VIRTUAL_NODES):
                key = self._hash(f"{node}#{i}")
                self.ring[key] = node
        self.sorted_keys = sorted(self.ring.keys())

    def _hash(self, key: str) -> int:
        """Fungsi hashing SHA1 sederhana."""
        return int(hashlib.sha1(key.encode()).hexdigest(), 16) % HASH_SPACE

    def get_node(self, key: str) -> Optional[str]:
        """Menemukan node yang bertanggung jawab atas kunci (topic)."""
        if not self.ring:
            return None
            
        key_hash = self._hash(key)
        
        # Temukan titik hash pertama di ring yang >= key_hash
        pos = bisect.bisect_left(self.sorted_keys, key_hash)
        
        # Wrap around: Jika melewati akhir ring, kembali ke awal
        if pos == len(self.sorted_keys):
            pos = 0
            
        return self.ring[self.sorted_keys[pos]]

# --- Distributed Queue Node Implementation ---

class DistributedQueueNode:
    """Implementasi Distributed Queue dengan Message Persistence dan At-Least-Once Delivery."""
    
    # Prefix kunci Redis
    QUEUE_PREFIX = "q:"
    PENDING_PREFIX = "pending_q:"
    META_SUFFIX = "_meta"
    REDELIVERY_TIMEOUT = 30 # detik untuk timeout ACK

    def __init__(self, node_id: str, ring: ConsistentHashRing, redis_host: str = 'redis', redis_port: int = 6379):
        self.node_id = node_id
        self.ring = ring
        # Koneksi Redis untuk Message Persistence
        self.redis_conn = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)

    async def publish(self, topic: str, message_data: Dict[str, Any]):
        """
        Producer API: Menerima pesan dan merutekannya ke Queue Node yang bertanggung jawab.
        """
        responsible_node_id = self.ring.get_node(topic)
        
        if responsible_node_id is None:
             return {"status": "FAILURE", "error": "No nodes available"}

        if responsible_node_id != self.node_id:
            # Di implementasi nyata, ini akan menjadi RPC ke node yang benar
            return {"status": "REDIRECT", "node": responsible_node_id}

        # Message Persistence: Pesan disimpan dalam Redis List (FIFO: Rpush)
        message_id = hashlib.sha1(f"{topic}-{time.time()}".encode()).hexdigest()[:10]
        message = {
            "id": message_id,
            "timestamp": time.time(),
            "data": message_data,
            "topic": topic
        }
        
        # Simpan pesan ke antrian utama
        self.redis_conn.rpush(f"{self.QUEUE_PREFIX}{topic}", json.dumps(message))
        return {"status": "SUCCESS", "message_id": message["id"], "node": self.node_id}

    async def consume(self, topic: str):
        """
        Consumer API: Mengambil pesan dari antrian utama dan memindahkannya ke Pending Queue.
        Ini adalah bagian dari At-Least-Once Delivery.
        """
        responsible_node_id = self.ring.get_node(topic)
        if responsible_node_id != self.node_id:
            return {"status": "REDIRECT", "node": responsible_node_id}
            
        queue_key = f"{self.QUEUE_PREFIX}{topic}"
        pending_key = f"{self.PENDING_PREFIX}{topic}"
        meta_key = f"{pending_key}{self.META_SUFFIX}"
        
        # Atomik: pindahkan pesan dari antrian utama ke antrian pending
        message_str = self.redis_conn.rpoplpush(queue_key, pending_key)
        
        if message_str:
            message = json.loads(message_str)
            message["sent_time"] = time.time() # Catat waktu pengiriman untuk Redelivery
            
            # Simpan metadata pesan pending
            self.redis_conn.hset(meta_key, message["id"], json.dumps(message))
            
            return {"status": "MESSAGE_SENT", "message": message}
        
        return {"status": "NO_MESSAGE"}

    async def acknowledge(self, topic: str, message_id: str):
        """
        Consumer API: Mengakui bahwa pesan telah berhasil diproses.
        Menghapus pesan dari Pending Queue.
        """
        pending_key = f"{self.PENDING_PREFIX}{topic}"
        meta_key = f"{pending_key}{self.META_SUFFIX}"
        
        # 1. Ambil string pesan dari metadata
        message_str = self.redis_conn.hget(meta_key, message_id)
        
        if message_str:
            # Transaksi Redis untuk atomisitas (hapus dari meta dan dari list)
            pipe = self.redis_conn.pipeline()
            
            # 2. Hapus metadata
            pipe.hdel(meta_key, message_id)
            
            # 3. Hapus pesan dari list pending
            pipe.lrem(pending_key, 1, message_str)
            
            pipe.execute()
            return {"status": "ACK_RECEIVED", "message_id": message_id}
            
        return {"status": "ACK_NOT_FOUND"}

    async def redelivery_monitor(self):
        """
        Tugas latar belakang untuk memantau pesan yang dikirim tetapi tidak di-ACK dalam timeout.
        Memastikan At-Least-Once Delivery.
        """
        while True:
            # Cari semua kunci metadata pending
            for meta_key in self.redis_conn.keys(f"{self.PENDING_PREFIX}*{self.META_SUFFIX}"):
                
                # Ekstrak nama pending_key dan topic
                topic = meta_key.split(self.PENDING_PREFIX)[1].replace(self.META_SUFFIX, "")
                pending_key = f"{self.PENDING_PREFIX}{topic}"
                
                # Hanya jalankan monitor jika node ini yang bertanggung jawab
                if self.ring.get_node(topic) != self.node_id:
                    continue

                # Ambil semua pesan pending
                pending_messages = self.redis_conn.hgetall(meta_key)
                now = time.time()
                
                for msg_id, msg_str in pending_messages.items():
                    msg = json.loads(msg_str)
                    
                    if now - msg.get("sent_time", 0) > self.REDELIVERY_TIMEOUT:
                        print(f"Redelivering message {msg_id} for topic {topic} due to timeout.")
                        
                        pipe = self.redis_conn.pipeline()
                        
                        # 1. Pindahkan kembali pesan ke antrian utama (q:topic)
                        pipe.lpush(f"{self.QUEUE_PREFIX}{topic}", msg_str)
                        
                        # 2. Hapus dari metadata pending
                        pipe.hdel(meta_key, msg_id)
                        
                        # 3. Hapus dari list pending
                        pipe.lrem(pending_key, 1, msg_str)
                        
                        pipe.execute()
                        
            await asyncio.sleep(self.REDELIVERY_TIMEOUT / 3) # Cek setiap 10 detik