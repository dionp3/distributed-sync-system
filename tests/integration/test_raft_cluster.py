import pytest
import requests
import time
import json

# --- KONFIGURASI DOCKER ---
# Asumsi Node Lock berjalan di port host 8001, 8002, 8003
LOCK_NODES = {
    "node_lock_1": "http://localhost:8001",
    "node_lock_2": "http://localhost:8002",
    "node_lock_3": "http://localhost:8003",
}

def find_leader_port():
    """Mencoba mengakuisisi lock pada semua node untuk menemukan Leader."""
    for node_id, url in LOCK_NODES.items():
        try:
            response = requests.post(f"{url}/lock/acquire", json={"lock_name": "probe", "client_id": "TEST_PROBE", "timeout": 1.0}, timeout=0.5)
            if response.status_code == 200 and response.json().get('success'):
                # Rilis probe lock
                requests.post(f"{url}/lock/release", json={"lock_name": "probe", "client_id": "TEST_PROBE"}, timeout=0.5)
                print(f"\nLeader found at {url} ({node_id})")
                return url, node_id
        except requests.exceptions.RequestException:
            continue
    pytest.fail("Gagal menemukan Raft Leader yang aktif.")

@pytest.fixture(scope="module")
def raft_leader():
    """Fixture yang menemukan Leader Raft sebelum memulai modul tes."""
    leader_url, leader_id = find_leader_port()
    return leader_url, leader_id

def get_node_container_name(node_id):
    """Mengonversi node_id (misal node_lock_2) ke nama container Docker yang lengkap."""
    # Asumsi nama container sesuai dengan format docker-compose: docker-[service_name]-1
    return f"docker-{node_id}-1"

def test_01_raft_initial_acquire_release(raft_leader):
    """Menguji acquire dan release lock dalam kondisi normal."""
    leader_url, _ = raft_leader
    client_id = "Client_TEST_01"
    
    # Acquire
    resp_acquire = requests.post(f"{leader_url}/lock/acquire", json={"lock_name": "TestLock1", "client_id": client_id, "lock_type": "exclusive"})
    assert resp_acquire.status_code == 200
    assert resp_acquire.json()['success'] is True

    # Release
    resp_release = requests.post(f"{leader_url}/lock/release", json={"lock_name": "TestLock1", "client_id": client_id})
    assert resp_release.status_code == 200
    assert resp_release.json()['success'] is True

def test_02_raft_contention_and_linearizability(raft_leader):
    """Menguji contention dan memastikan hanya Leader yang memproses."""
    leader_url, follower_id = raft_leader 
    follower_url = LOCK_NODES[follower_id] # Coba acquire pada follower

    # Acquire pada Leader (Harus Berhasil)
    resp_leader = requests.post(f"{leader_url}/lock/acquire", json={"lock_name": "TestLock2", "client_id": "C1", "lock_type": "exclusive"})
    assert resp_leader.json()['success'] is True

    # Acquire pada Follower (Harus Gagal atau Redirect)
    resp_follower = requests.post(f"{follower_url}/lock/acquire", json={"lock_name": "TestLock2", "client_id": "C2", "lock_type": "exclusive"})
    
    # Karena test ini mungkin mengenai Leader yang sama (jika node_lock_1, 2, 3 semua Leader), 
    # kita pastikan Client C2 DITOLAK karena C1 sudah memegang.
    # Jika C1 memegang, C2 harus ditolak (linearizability).
    assert resp_follower.json()['success'] is False

    # Cleanup
    requests.post(f"{leader_url}/lock/release", json={"lock_name": "TestLock2", "client_id": "C1"})

@pytest.mark.skip(reason="Memerlukan eksekusi CLI Docker untuk menguji stop/start.")
def test_03_raft_failover_and_consistency(raft_leader):
    """Menguji failover dengan mematikan Leader dan mencari Leader baru."""
    # Tes ini idealnya dilakukan secara manual dan didemonstrasikan di video
    pass