import pytest
import requests
import json

# --- KONFIGURASI DOCKER ---
# Asumsi Node Lock/Queue/Cache berjalan di port 8001, 8011, 8021
API_URLS = {
    "LOCK": "http://localhost:8001",
    "QUEUE": "http://localhost:8011",
    "CACHE": "http://localhost:8021",
}
HEADERS = {"Content-Type": "application/json"}

# --- UTILITY: Coba temukan Leader untuk tes yang memerlukan Leader ---
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
    """Menguji publish pesan dan endpoint /metrics Queue."""
    queue_url = API_URLS['QUEUE']
    
    # Tes Publish (Harus 200 OK)
    resp_pub = requests.post(f"{queue_url}/queue/publish", headers=HEADERS, json={"topic": "T1", "data": {"key": 1}})    
    assert resp_pub.status_code == 200
    
    # PERBAIKAN: Terima SUCCESS atau REDIRECT sebagai hasil yang valid
    status = resp_pub.json().get('status')
    assert status in ("SUCCESS", "REDIRECT")

    # Tes Metrics (Harus 200 OK dan text/plain)
    resp_metrics = requests.get(f"{queue_url}/metrics")
    assert resp_metrics.status_code == 200
    assert "text/plain" in resp_metrics.headers['Content-Type']
    assert "queue_node_status" in resp_metrics.text


def test_02_lock_acquire_and_redirect_behavior():
    """Menguji acquire lock dan respons redirect (jika bukan Leader)."""
    leader_url = find_leader_url() 
    if not leader_url:
        pytest.skip("No Leader found.")
        
    # Tes Acquire pada Leader (Harus 200 OK)
    resp_acquire = requests.post(f"{leader_url}/lock/acquire", headers=HEADERS, json={"lock_name": "T02", "client_id": "C1", "timeout": 5.0})    
    if resp_acquire.json().get('error') == 'NOT_LEADER':
        # Skip jika Leader sudah pindah sejak find_leader_url() dipanggil
        pytest.skip("Leader changed during the test execution.")
    
    assert resp_acquire.json()['success'] is True
    
    # Tes Acquire pada Follower (Simulasi 307 Redirect atau NOT_LEADER)
    # Kita tidak tahu pasti port mana yang Follower, jadi kita coba port 8002
    resp_follower = requests.post("http://localhost:8002/lock/acquire", headers=HEADERS, json={"lock_name": "T03", "client_id": "C2"})
    
    # Raft Integration Test: Response harus NOT_LEADER (307 jika logic redirect ada, 200 jika NOT_LEADER di body)
    assert resp_follower.json()['success'] is False or resp_follower.status_code == 307
    
    # Cleanup
    requests.post(f"{leader_url}/lock/release", headers=HEADERS, json={"lock_name": "T02", "client_id": "C1"})


def test_03_cache_read_and_write_status():
    """Menguji status codes dasar untuk Cache Read/Write."""
    cache_url = API_URLS['CACHE']
    
    # Tes Write
    resp_write = requests.post(f"{cache_url}/cache/write", headers=HEADERS, json={"key": "K1", "value": "Test"})
    assert resp_write.status_code == 200
    assert "WRITE" in resp_write.json()['status']

    # Tes Read
    resp_read = requests.post(f"{cache_url}/cache/read", headers=HEADERS, json={"key": "K1"})
    assert resp_read.status_code == 200
    assert resp_read.json()['status'] == "HIT" # Seharusnya HIT setelah Write
    assert resp_read.json()['value'] == "Test"