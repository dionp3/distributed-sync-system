import pytest
from src.nodes.queue_node import ConsistentHashRing
from src.nodes.cache_node import DistributedCacheNode, CacheState # Import yang diperlukan

TEST_NODES = ["node1", "node2", "node3"]

@pytest.fixture
def hash_ring():
    return ConsistentHashRing(TEST_NODES)

def test_ring_initialization_and_size(hash_ring):
    from src.nodes.queue_node import VIRTUAL_NODES
    assert len(hash_ring.ring) == len(TEST_NODES) * VIRTUAL_NODES
    assert len(hash_ring.sorted_keys) == len(TEST_NODES) * VIRTUAL_NODES

def test_get_node_consistency(hash_ring):
    key = "user_session_123"
    node_a = hash_ring.get_node(key)
    node_b = hash_ring.get_node(key)
    assert node_a == node_b
    assert node_a in TEST_NODES

def test_node_addition_minimal_resharding():
    ring_old = ConsistentHashRing(["A", "B", "C"])
    ring_new = ConsistentHashRing(["A", "B", "C", "D"])
    
    keys_to_check = ["item_1", "item_2", "item_3", "item_100"]
    
    moved_count = 0
    for key in keys_to_check:
        node_old = ring_old.get_node(key)
        node_new = ring_new.get_node(key)
        
        if node_old != node_new and node_old != "D":
            moved_count += 1
            
    assert "D" in ring_new.nodes
    assert moved_count < len(keys_to_check) * 0.5 

def test_lru_eviction_order():
    cache = DistributedCacheNode("test_lru", 3, comm=None, redis_host="dummy")
    
    cache._add_or_update("A", 1, CacheState.EXCLUSIVE) 
    cache._add_or_update("B", 2, CacheState.SHARED)
    cache._add_or_update("C", 3, CacheState.MODIFIED)
    
    cache._update_lru("A") 
    
    cache._add_or_update("D", 4, CacheState.EXCLUSIVE)
    
    assert "B" not in cache.cache
    assert len(cache.cache) == 3
    
    first_key = next(iter(cache.cache))
    assert first_key == "C" 
    assert "A" in cache.cache
    assert "D" in cache.cache