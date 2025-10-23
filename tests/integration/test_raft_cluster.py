import pytest
import requests
import json
import time

LOCK_NODES = {
    "node_lock_1": "http://localhost:8001",
    "node_lock_2": "http://localhost:8002",
    "node_lock_3": "http://localhost:8003",
}

def find_leader_port():
    for node_id, url in LOCK_NODES.items():
        try:
            response = requests.post(f"{url}/lock/acquire", json={"lock_name": "probe", "client_id": "TEST_PROBE", "timeout": 0.5}, timeout=0.5)
            if response.status_code == 200 and response.json().get('success'):
                requests.post(f"{url}/lock/release", json={"lock_name": "probe", "client_id": "TEST_PROBE"}, timeout=0.5)
                return url, node_id
        except requests.exceptions.RequestException:
            continue
    pytest.fail("Gagal menemukan Raft Leader yang aktif.")

@pytest.fixture(scope="module")
def raft_leader():
    leader_url, leader_id = find_leader_port()
    return leader_url, leader_id

def test_01_raft_initial_acquire_release(raft_leader):
    leader_url, _ = raft_leader
    client_id = "Client_TEST_01"
    
    resp_acquire = requests.post(f"{leader_url}/lock/acquire", json={"lock_name": "TestLock1", "client_id": client_id, "lock_type": "exclusive"})
    assert resp_acquire.status_code == 200
    assert resp_acquire.json()['success'] is True

    resp_release = requests.post(f"{leader_url}/lock/release", json={"lock_name": "TestLock1", "client_id": client_id})
    assert resp_release.status_code == 200
    assert resp_release.json()['success'] is True

def test_02_raft_contention_and_linearizability(raft_leader):
    leader_url, leader_id = raft_leader 
    
    resp_leader = requests.post(f"{leader_url}/lock/acquire", json={"lock_name": "TestLock2", "client_id": "C1", "lock_type": "exclusive"})
    assert resp_leader.json()['success'] is True

    follower_url_assume = LOCK_NODES["node_lock_2"] 
    resp_follower = requests.post(f"{follower_url_assume}/lock/acquire", json={"lock_name": "TestLock2", "client_id": "C2", "lock_type": "exclusive"})
    
    if leader_url == follower_url_assume and resp_follower.json()['success'] is True:
        pytest.fail("Logika kontradiksi: Kedua klien berhasil mendapatkan lock yang sama secara bersamaan.")
    
    assert resp_follower.json()['success'] is False

    requests.post(f"{leader_url}/lock/release", json={"lock_name": "TestLock2", "client_id": "C1"})

@pytest.mark.skip(reason="Memerlukan eksekusi CLI Docker untuk menguji stop/start.")
def test_03_raft_failover_and_consistency(raft_leader):
    pass