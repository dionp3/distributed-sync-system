import redis
import json
import time
import hashlib
import bisect
import asyncio
from typing import List, Dict, Any, Optional

VIRTUAL_NODES = 100 
HASH_SPACE = 2**32

class ConsistentHashRing:
    def __init__(self, nodes: List[str]):
        self.nodes = nodes
        self.ring: Dict[int, str] = {}
        self.sorted_keys: List[int] = []
        if nodes:
            self._build_ring()

    def _build_ring(self):
        self.ring.clear()
        for node in self.nodes:
            for i in range(VIRTUAL_NODES):
                key = self._hash(f"{node}#{i}")
                self.ring[key] = node
        self.sorted_keys = sorted(self.ring.keys())

    def _hash(self, key: str) -> int:
        return int(hashlib.sha1(key.encode()).hexdigest(), 16) % HASH_SPACE

    def get_node(self, key: str) -> Optional[str]:
        if not self.ring:
            return None
            
        key_hash = self._hash(key)
        pos = bisect.bisect_left(self.sorted_keys, key_hash)
        
        if pos == len(self.sorted_keys):
            pos = 0
            
        return self.ring[self.sorted_keys[pos]]

class DistributedQueueNode:
    QUEUE_PREFIX = "q:"
    PENDING_PREFIX = "pending_q:"
    META_SUFFIX = "_meta"
    REDELIVERY_TIMEOUT = 30

    def __init__(self, node_id: str, ring: ConsistentHashRing, redis_host: str = 'redis', redis_port: int = 6379):
        self.node_id = node_id
        self.ring = ring
        self.redis_conn = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)

    async def publish(self, topic: str, message_data: Dict[str, Any]):
        responsible_node_id = self.ring.get_node(topic)
        
        if responsible_node_id is None:
             return {"status": "FAILURE", "error": "No nodes available"}

        if responsible_node_id != self.node_id:
            return {"status": "REDIRECT", "node": responsible_node_id}

        message_id = hashlib.sha1(f"{topic}-{time.time()}".encode()).hexdigest()[:10]
        message = {
            "id": message_id,
            "timestamp": time.time(),
            "data": message_data,
            "topic": topic
        }
        
        self.redis_conn.rpush(f"{self.QUEUE_PREFIX}{topic}", json.dumps(message))
        return {"status": "SUCCESS", "message_id": message["id"], "node": self.node_id}

    async def consume(self, topic: str):
        responsible_node_id = self.ring.get_node(topic)
        if responsible_node_id != self.node_id:
            return {"status": "REDIRECT", "node": responsible_node_id}
            
        queue_key = f"{self.QUEUE_PREFIX}{topic}"
        pending_key = f"{self.PENDING_PREFIX}{topic}"
        meta_key = f"{pending_key}{self.META_SUFFIX}"
        
        message_str = self.redis_conn.rpoplpush(queue_key, pending_key)
        
        if message_str:
            message = json.loads(message_str)
            message["sent_time"] = time.time()
            
            self.redis_conn.hset(meta_key, message["id"], json.dumps(message))
            
            return {"status": "MESSAGE_SENT", "message": message}
        
        return {"status": "NO_MESSAGE"}

    async def acknowledge(self, topic: str, message_id: str):
        pending_key = f"{self.PENDING_PREFIX}{topic}"
        meta_key = f"{pending_key}{self.META_SUFFIX}"
        
        message_str = self.redis_conn.hget(meta_key, message_id)
        
        deleted_count = self.redis_conn.hdel(meta_key, message_id)
        
        if deleted_count > 0 and message_str:
            pipe = self.redis_conn.pipeline()
            
            pipe.lrem(pending_key, 1, message_str) 
            
            pipe.execute()
            return {"status": "ACK_RECEIVED", "message_id": message_id}
            
        return {"status": "ACK_NOT_FOUND"}

    async def redelivery_monitor(self):
        while True:
            for meta_key in self.redis_conn.keys(f"{self.PENDING_PREFIX}*{self.META_SUFFIX}"):
                
                topic = meta_key.split(self.PENDING_PREFIX)[1].replace(self.META_SUFFIX, "")
                pending_key = f"{self.PENDING_PREFIX}{topic}"
                
                if self.ring.get_node(topic) != self.node_id:
                    continue

                pending_messages = self.redis_conn.hgetall(meta_key)
                now = time.time()
                
                for msg_id, msg_str in pending_messages.items():
                    msg = json.loads(msg_str)
                    
                    if now - msg.get("sent_time", 0) > self.REDELIVERY_TIMEOUT:
                        print(f"Redelivering message {msg_id} for topic {topic} due to timeout.")
                        
                        pipe = self.redis_conn.pipeline()
                        
                        pipe.lpush(f"{self.QUEUE_PREFIX}{topic}", msg_str)
                        pipe.hdel(meta_key, msg_id)
                        pipe.lrem(pending_key, 1, msg_str)
                        
                        pipe.execute()
                        
            await asyncio.sleep(self.REDELIVERY_TIMEOUT / 3)