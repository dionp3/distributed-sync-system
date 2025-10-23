import pytest
from unittest.mock import MagicMock
from src.nodes.cache_node import DistributedCacheNode, CacheState

@pytest.fixture
def lru_cache_full():
    """Membuat cache dengan max_size=3 dan mengisinya."""
    # Mock comm dan redis_host tidak diperlukan untuk unit test LRU
    cache = DistributedCacheNode("test_lru", max_size=3, comm=None, redis_host="dummy")
    
    # Tambahkan item A, B, C secara berurutan (B adalah yang paling lama digunakan)
    cache._add_or_update("A", 1, CacheState.EXCLUSIVE) 
    cache._add_or_update("B", 2, CacheState.SHARED)
    cache._add_or_update("C", 3, CacheState.MODIFIED)
    
    # Akses A, memindahkannya ke belakang (paling baru digunakan)
    cache._update_lru("A")
    
    return cache

def test_cache_size_initial(lru_cache_full):
    """Memastikan cache terisi penuh."""
    assert len(lru_cache_full.cache) == 3

def test_lru_update_on_access(lru_cache_full):
    """Memastikan item yang diakses menjadi yang terakhir di OrderedDict."""
    # Setelah akses A, A harus menjadi kunci terakhir. Item pertama adalah B
    first_key = next(iter(lru_cache_full.cache))
    last_key = list(lru_cache_full.cache.keys())[-1]
    
    assert first_key == "B"
    assert last_key == "A"

def test_lru_eviction_on_add(lru_cache_full):
    """Menguji penambahan item baru memicu eviction item terlama (B)."""
    
    # B adalah yang paling lama digunakan. Menambahkan 'D' harus meng-evict 'B'.
    lru_cache_full._add_or_update("D", 4, CacheState.EXCLUSIVE)
    
    # 1. Cek ukuran
    assert len(lru_cache_full.cache) == 3 
    
    # 2. Cek item yang di-evict
    assert "B" not in lru_cache_full.cache
    assert "D" in lru_cache_full.cache
    
    # 3. Cek urutan baru (C harus menjadi yang terlama)
    first_key = next(iter(lru_cache_full.cache))
    assert first_key == "C"

def test_write_back_on_modified_eviction():
    """Menguji write-back dipanggil jika item berstatus Modified."""
    cache = DistributedCacheNode("test_wb", max_size=1, comm=None, redis_host="dummy")
    
    # Mock write_back agar kita tahu kapan dipanggil
    cache._write_back = MagicMock() 
    
    # Tambahkan item M1 (Modified)
    cache._add_or_update("M1", "data_v1", CacheState.MODIFIED)
    
    # Tambahkan item baru (harus meng-evict M1)
    cache._add_or_update("A2", "data_v2", CacheState.EXCLUSIVE)
    
    # Verifikasi _write_back dipanggil
    cache._write_back.assert_called_once_with("M1", "data_v1")