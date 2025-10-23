import pytest
from src.nodes.queue_node import ConsistentHashRing # Asumsi import benar

# Nodes untuk pengujian
TEST_NODES = ["node1", "node2", "node3"]

@pytest.fixture
def hash_ring():
    """Membuat instance ConsistentHashRing."""
    return ConsistentHashRing(TEST_NODES)

def test_ring_initialization_and_size(hash_ring):
    """Memastikan ring terinisialisasi dengan virtual nodes."""
    from src.nodes.queue_node import VIRTUAL_NODES
    assert len(hash_ring.ring) == len(TEST_NODES) * VIRTUAL_NODES
    assert len(hash_ring.sorted_keys) == len(TEST_NODES) * VIRTUAL_NODES

def test_get_node_consistency(hash_ring):
    """Memastikan kunci yang sama selalu di-map ke node yang sama."""
    key = "user_session_123"
    node_a = hash_ring.get_node(key)
    node_b = hash_ring.get_node(key)
    assert node_a == node_b
    assert node_a in TEST_NODES

def test_node_addition_minimal_resharding():
    """Menguji minimalnya resharding saat node baru ditambahkan."""
    ring_old = ConsistentHashRing(["A", "B", "C"])
    ring_new = ConsistentHashRing(["A", "B", "C", "D"])
    
    keys_to_check = ["item_1", "item_2", "item_3", "item_100"]
    
    moved_count = 0
    for key in keys_to_check:
        node_old = ring_old.get_node(key)
        node_new = ring_new.get_node(key)
        
        if node_old != node_new and node_old != "D":
            moved_count += 1
            
    # Dalam consistent hashing, seharusnya hanya sebagian kecil yang pindah
    # Note: Karena VIRTUAL_NODES tinggi, kita hanya cek jika penambahan Node D berhasil.
    assert "D" in ring_new.nodes
    assert moved_count < len(keys_to_check) * 0.5 

def test_lru_eviction_order():
    """Menguji apakah LRU meng-evict item yang paling lama tidak diakses."""
    from src.nodes.cache_node import DistributedCacheNode
    
    # max_size = 3
    cache = DistributedCacheNode("test_lru", 3, comm=None, redis_host="dummy")
    
    # 1. Tambahkan 3 item (A, B, C)
    cache._add_or_update("A", 1, None)
    cache._add_or_update("B", 2, None)
    cache._add_or_update("C", 3, None)
    
    # 2. Akses A (membuat A menjadi paling baru digunakan)
    cache._update_lru("A") 
    
    # 3. Tambahkan D (ini harus meng-evict item paling lama: B atau C. Seharusnya B)
    # Catatan: Karena LRU menggunakan OrderedDict dan kita update_lru("A"), urutan LAMA -> BARU adalah B, C, A.
    cache._add_or_update("D", 4, None)
    
    assert "B" not in cache.cache # B harus di-evict
    assert "A" in cache.cache
    assert "C" in cache.cache
    assert "D" in cache.cache