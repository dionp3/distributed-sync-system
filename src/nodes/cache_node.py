import time
import json
import redis
import asyncio 
from enum import Enum
from collections import OrderedDict
from typing import Dict, Any, List, Optional
from src.communication.message_passing import NodeCommunication

class CacheState(Enum):
    INVALID = 'I'
    SHARED = 'S'
    EXCLUSIVE = 'E'
    MODIFIED = 'M'

class CacheLine:
    def __init__(self, key: str, value: Any, state: CacheState):
        self.key = key
        self.value = value
        self.state = state
        self.last_used = time.time()

class DistributedCacheNode:
    def __init__(self, node_id: str, max_size: int, comm: NodeCommunication, redis_host: str = 'redis', redis_port: int = 6379):
        self.node_id = node_id
        self.max_size = max_size
        self.comm = comm 
        
        self.cache: OrderedDict[str, CacheLine] = OrderedDict() 
        self.metrics = {'hits': 0, 'misses': 0, 'invalidations_sent': 0, 'invalidations_received': 0, 'writebacks': 0}
        
        self.main_memory = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)

    def _update_lru(self, key: str):
        if key in self.cache:
            self.cache.move_to_end(key)
            self.cache[key].last_used = time.time()

    def _write_back(self, key: str, value: Any):
        self.metrics['writebacks'] += 1
        self.main_memory.set(key, value)
        print(f"CACHE {self.node_id}: WRITEBACK {key} -> Main Memory.")

    async def _broadcast_invalidate(self, key: str):
        self.metrics['invalidations_sent'] += 1
        payload = {'key': key}
        await self.comm.broadcast_rpc('/cache/invalidate', payload)
        print(f"CACHE {self.node_id}: Broadcasting INVAL for {key}")

    def _add_or_update(self, key: str, value: Any, state: CacheState):
        if key not in self.cache and len(self.cache) >= self.max_size:
            lru_key, lru_line = self.cache.popitem(last=False) 
            
            if lru_line.state == CacheState.MODIFIED:
                self._write_back(lru_key, lru_line.value)
            
            print(f"CACHE {self.node_id}: LRU Eviction -> {lru_key}")
                
        self.cache[key] = CacheLine(key, value, state)
        self._update_lru(key)

    async def read(self, key: str):
        if key in self.cache:
            line = self.cache[key]
            if line.state != CacheState.INVALID:
                self.metrics['hits'] += 1
                self._update_lru(key)
                print(f"CACHE {self.node_id}: READ HIT on {key} (State: {line.state.value})")
                return {"status": "HIT", "value": line.value}

        self.metrics['misses'] += 1
        print(f"CACHE {self.node_id}: READ MISS on {key}. Fetching from Memory.")
        
        value = self.main_memory.get(key)
        
        if value is not None:
            new_state = CacheState.SHARED 
            
            self._add_or_update(key, value, new_state)
            return {"status": "MISS_FETCHED", "value": value}
        
        return {"status": "MISS_NOT_FOUND"}

    async def write(self, key: str, value: Any):
        if key in self.cache and self.cache[key].state != CacheState.INVALID:
            line = self.cache[key]
            
            if line.state in (CacheState.EXCLUSIVE, CacheState.MODIFIED):
                line.value = value
                line.state = CacheState.MODIFIED
                self._update_lru(key)
                return {"status": "WRITE_HIT_MODIFIED"}

            elif line.state == CacheState.SHARED:
                line.value = value
                line.state = CacheState.MODIFIED
                self._update_lru(key)
                await self._broadcast_invalidate(key)
                return {"status": "WRITE_HIT_INVALIDATING"}
        
        self.main_memory.set(key, value)
        self._add_or_update(key, value, CacheState.MODIFIED)
        await self._broadcast_invalidate(key)
        
        return {"status": "WRITE_MISS_INVALIDATING"}

    def handle_invalidation(self, key: str):
        self.metrics['invalidations_received'] += 1
        
        if key in self.cache:
            line = self.cache[key]
            
            if line.state == CacheState.MODIFIED:
                self._write_back(key, line.value)
            
            line.state = CacheState.INVALID
            print(f"CACHE {self.node_id}: Received INVAL for {key}. State -> I")
        
    def get_metrics(self) -> Dict[str, Any]:
        total = self.metrics['hits'] + self.metrics['misses']
        hit_rate = self.metrics['hits'] / total if total > 0 else 0
        return {
            'node_id': self.node_id,
            'hit_rate': round(hit_rate, 4),
            'size': len(self.cache),
            'capacity': self.max_size,
            **self.metrics
        }