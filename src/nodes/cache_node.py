import time
import json
import redis
from enum import Enum
from collections import OrderedDict
from typing import Dict, Any, List
from src.communication.message_passing import NodeCommunication # Asumsi impor ini benar

# State Cache Coherence (MESI)
class CacheState(Enum):
    INVALID = 'I'     # Data tidak valid/belum ada
    SHARED = 'S'      # Data bersih dan mungkin dimiliki cache lain
    EXCLUSIVE = 'E'   # Data bersih, hanya dimiliki cache ini, tidak ada di cache lain
    MODIFIED = 'M'    # Data kotor (diubah), hanya dimiliki cache ini

class CacheLine:
    """Representasi satu baris data dalam cache."""
    def __init__(self, key: str, value: Any, state: CacheState):
        self.key = key
        self.value = value
        self.state = state
        self.last_used = time.time() # Untuk LRU

class DistributedCacheNode:
    """
    Mengimplementasikan Cache Coherence MESI dan LRU Replacement Policy.
    Menggunakan Redis sebagai simulasi Memori Utama.
    """
    def __init__(self, node_id: str, max_size: int, comm: NodeCommunication, redis_host: str = 'redis', redis_port: int = 6379):
        self.node_id = node_id
        self.max_size = max_size
        self.comm = comm 
        
        # Cache: OrderedDict digunakan untuk mengelola LRU (Least Recently Used)
        # {key: CacheLine}
        self.cache: OrderedDict[str, CacheLine] = OrderedDict() 
        self.metrics = {'hits': 0, 'misses': 0, 'invalidations_sent': 0, 'invalidations_received': 0, 'writebacks': 0}
        
        # Memori Utama (Redis)
        self.main_memory = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)

    def _update_lru(self, key: str):
        """Update posisi LRU (pindahkan ke akhir OrderedDict)."""
        if key in self.cache:
            self.cache.move_to_end(key)
            self.cache[key].last_used = time.time()

    def _write_back(self, key: str, value: Any):
        """Menulis data kembali ke Memori Utama (Redis)."""
        self.metrics['writebacks'] += 1
        self.main_memory.set(key, value)
        print(f"CACHE {self.node_id}: WRITEBACK {key} -> Main Memory.")

    async def _broadcast_invalidate(self, key: str):
        """Mengirim pesan Invalidate ke semua Cache Node lain."""
        self.metrics['invalidations_sent'] += 1
        payload = {'key': key}
        # Endpoint /cache/invalidate harus diimplementasikan di main.py setiap peer
        await self.comm.broadcast_rpc('/cache/invalidate', payload)
        print(f"CACHE {self.node_id}: Broadcasting INVAL for {key}")

    def _add_or_update(self, key: str, value: Any, state: CacheState):
        """Menambahkan atau memperbarui baris cache, menerapkan LRU jika cache penuh."""
        
        # 1. LRU Replacement Policy
        if key not in self.cache and len(self.cache) >= self.max_size:
            # Pop item paling awal (Least Recently Used)
            lru_key, lru_line = self.cache.popitem(last=False) 
            
            if lru_line.state == CacheState.MODIFIED:
                # Jika kotor, harus Write Back sebelum diganti
                self._write_back(lru_key, lru_line.value)
            
            print(f"CACHE {self.node_id}: LRU Eviction -> {lru_key}")
                
        # 2. Tambahkan/Update item baru
        self.cache[key] = CacheLine(key, value, state)
        self._update_lru(key) # Pindahkan ke akhir (paling baru digunakan)

    # --- Operasi Utama Cache ---

    async def read(self, key: str):
        """Membaca data. Mencegah race condition/stale data."""
        if key in self.cache:
            line = self.cache[key]
            if line.state != CacheState.INVALID:
                self.metrics['hits'] += 1
                self._update_lru(key)
                print(f"CACHE {self.node_id}: READ HIT on {key} (State: {line.state.value})")
                return {"status": "HIT", "value": line.value}

        # Cache Miss (State I)
        self.metrics['misses'] += 1
        print(f"CACHE {self.node_id}: READ MISS on {key}. Fetching from Memory.")
        
        # Skenario: MISS (I -> S/E)
        
        # 1. Ambil data dari Memori Utama (Redis)
        value = self.main_memory.get(key)
        
        if value is not None:
            # Dalam sistem nyata, perlu cek cache lain (Snooping).
            # Karena ini simulasi, asumsikan default ke SHARED (S) jika ada di memory.
            new_state = CacheState.SHARED 
            
            self._add_or_update(key, value, new_state)
            return {"status": "MISS_FETCHED", "value": value}
        
        return {"status": "MISS_NOT_FOUND"}


    async def write(self, key: str, value: Any):
        """Menulis/Memperbarui data. Memerlukan kepemilikan Exclusive/Modified."""
        
        # 1. Cek Hit/Miss
        if key in self.cache and self.cache[key].state != CacheState.INVALID:
            line = self.cache[key]
            
            if line.state in (CacheState.EXCLUSIVE, CacheState.MODIFIED):
                # E/M -> MODIFIED (Write Hit, tidak perlu Invalidasi)
                line.value = value
                line.state = CacheState.MODIFIED
                self._update_lru(key)
                return {"status": "WRITE_HIT_MODIFIED"}

            elif line.state == CacheState.SHARED:
                # S -> MODIFIED (Write Hit, Harus Invalidasi Cache Lain)
                line.value = value
                line.state = CacheState.MODIFIED
                self._update_lru(key)
                await self._broadcast_invalidate(key) # Broadcast
                return {"status": "WRITE_HIT_INVALIDATING"}
        
        # 2. Write Miss (I -> MODIFIED)
        
        # Langsung tulis data, asumsikan kepemilikan penuh (Modified)
        # dan sebarkan invalidasi.
        self.main_memory.set(key, value) # Write through ke memory
        self._add_or_update(key, value, CacheState.MODIFIED)
        await self._broadcast_invalidate(key)
        
        return {"status": "WRITE_MISS_INVALIDATING"}

    def handle_invalidation(self, key: str):
        """Dipanggil oleh RPC Handler ketika menerima pesan Invalidate dari peer."""
        self.metrics['invalidations_received'] += 1
        
        if key in self.cache:
            line = self.cache[key]
            
            if line.state == CacheState.MODIFIED:
                # M -> INVALID: Harus Write Back ke Memori Utama
                self._write_back(key, line.value)
            
            # Ubah state menjadi Invalid
            line.state = CacheState.INVALID
            print(f"CACHE {self.node_id}: Received INVAL for {key}. State -> I")
        
    def get_metrics(self) -> Dict[str, Any]:
        """Mengembalikan metrik performa untuk Prometheus."""
        total = self.metrics['hits'] + self.metrics['misses']
        hit_rate = self.metrics['hits'] / total if total > 0 else 0
        return {
            'node_id': self.node_id,
            'hit_rate': round(hit_rate, 4),
            'size': len(self.cache),
            'capacity': self.max_size,
            **self.metrics
        }