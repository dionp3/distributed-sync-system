import pytest
import requests
import json
from typing import Dict, Any

API_URLS = {
    "LOCK": "http://localhost:8001",
    "QUEUE": "http://localhost:8011",
    "CACHE": "http://localhost:8021",
}
HEADERS = {"Content-Type": "application/json"}

def find_leader_url():
    for port in [8001, 8002, 8003]:
        url = f"http://localhost:{port}"
        try:
            resp = requests.post(f"{url}/lock/acquire", json={"lock_name": "test_probe"}, timeout=0.5)
            if resp.status_code == 200:
                requests.post(f"{url}/lock/release", json={"lock_name": "test_probe"}, timeout=0.5)
                return url
        except:
            continue
    pytest.skip("Gagal menemukan Raft Leader aktif. Melewati tes Leader.")


def test_01_queue_publish_and_metrics_status():
    queue_url = API_URLS['QUEUE']
    
    resp_pub = requests.post(f"{queue_url}/queue/publish", headers=HEADERS, json={"topic": "T1", "data": {"key": 1}}) 
    status = resp_pub.json().get('status')
    assert resp_pub.status_code == 200
    assert status in ("SUCCESS", "REDIRECT")

    resp_metrics = requests.get(f"{queue_url}/metrics")
    assert resp_metrics.status_code == 200
    assert "text/plain" in resp_metrics.headers['Content-Type']
    assert "queue_node_status" in resp_metrics.text


def test_02_lock_acquire_and_redirect_behavior():
    leader_url = find_leader_url() 
    if not leader_url:
        pytest.skip("No Leader found.")
        
    resp_acquire = requests.post(f"{leader_url}/lock/acquire", headers=HEADERS, json={"lock_name": "T02", "client_id": "C1", "timeout": 5.0}) 
    
    if resp_acquire.json().get('error') == 'NOT_LEADER':
        pytest.skip("Leader changed during the test execution.")
    
    assert resp_acquire.json()['success'] is True
    
    resp_follower = requests.post("http://localhost:8002/lock/acquire", headers=HEADERS, json={"lock_name": "T03", "client_id": "C2"})
    
    assert resp_follower.json()['success'] is False or resp_follower.status_code == 307
    
    requests.post(f"{leader_url}/lock/release", headers=HEADERS, json={"lock_name": "T02", "client_id": "C1"})


def test_03_cache_read_and_write_status():
    cache_url = API_URLS['CACHE']
    
    resp_write = requests.post(f"{cache_url}/cache/write", headers=HEADERS, json={"key": "K1", "value": "Test"})
    assert resp_write.status_code == 200
    assert "WRITE" in resp_write.json()['status']

    resp_read = requests.post(f"{cache_url}/cache/read", headers=HEADERS, json={"key": "K1"})
    assert resp_read.status_code == 200
    assert resp_read.json()['status'] == "HIT"
    assert resp_read.json()['value'] == "Test"