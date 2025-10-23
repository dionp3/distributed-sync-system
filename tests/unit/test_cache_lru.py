import pytest
from unittest.mock import MagicMock
from src.nodes.cache_node import DistributedCacheNode, CacheState

@pytest.fixture
def lru_cache_full():
    cache = DistributedCacheNode("test_lru", max_size=3, comm=None, redis_host="dummy")
    
    cache._add_or_update("A", 1, CacheState.EXCLUSIVE) 
    cache._add_or_update("B", 2, CacheState.SHARED)
    cache._add_or_update("C", 3, CacheState.MODIFIED)
    
    cache._update_lru("A")
    
    return cache

def test_cache_size_initial(lru_cache_full):
    assert len(lru_cache_full.cache) == 3

def test_lru_update_on_access(lru_cache_full):
    first_key = next(iter(lru_cache_full.cache))
    last_key = list(lru_cache_full.cache.keys())[-1]
    
    assert first_key == "B"
    assert last_key == "A"

def test_lru_eviction_on_add(lru_cache_full):
    lru_cache_full._add_or_update("D", 4, CacheState.EXCLUSIVE)
    
    assert len(lru_cache_full.cache) == 3 
    
    assert "B" not in lru_cache_full.cache
    assert "D" in lru_cache_full.cache
    
    first_key = next(iter(lru_cache_full.cache))
    assert first_key == "C"

def test_write_back_on_modified_eviction():
    cache = DistributedCacheNode("test_wb", max_size=1, comm=None, redis_host="dummy")
    
    cache._write_back = MagicMock() 
    
    cache._add_or_update("M1", "data_v1", CacheState.MODIFIED)
    
    cache._add_or_update("A2", "data_v2", CacheState.EXCLUSIVE)
    
    cache._write_back.assert_called_once_with("M1", "data_v1")