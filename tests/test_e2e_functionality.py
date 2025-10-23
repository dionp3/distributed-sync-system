import requests
import json
import time
import os
import sys
import subprocess
from typing import Dict, Any, Optional, Tuple, List

PORTS: Dict[str, Any] = {
    "lock": [8001, 8002, 8003],
    "queue": 8011,
    "cache": [8021, 8022, 8023]
}
HEADERS: Dict[str, str] = {"Content-Type": "application/json"}
LOCK_TIMEOUT_SECS = 10
REDELIVERY_WAIT_SECS = 35


def find_leader_port() -> Optional[int]:
    probe_body = {"lock_name": "probe_lock", "client_id": "Python_Prober", "lock_type": "exclusive", "timeout": 1.0}
    
    print("--- Probing untuk Leader Raft ---")
    for port in PORTS['lock']:
        url = f"http://localhost:{port}/lock/acquire"
        try:
            response = requests.post(url, headers=HEADERS, json=probe_body, timeout=0.8)
            result = response.json()
            
            if response.status_code == 200 and result.get('success') is True:
                print(f"✅ LEADER DITEMUKAN: Port {port}. Merilis probe lock...")
                requests.post(f"http://localhost:{port}/lock/release", headers=HEADERS, json={"lock_name": "probe_lock", "client_id": "Python_Prober"}, timeout=0.5)
                return port
            elif result.get('error') == "NOT_LEADER":
                print(f"❌ Port {port} bukan Leader.")
            
        except requests.exceptions.RequestException:
            print(f"🛑 ERROR: Koneksi gagal ke port {port}.")
    
    print("⚠️ GAGAL menemukan Leader yang stabil.")
    return None

def check_log_for_event(container_name: str, keyword: str, timeout: int = 5) -> bool:
    command = f"docker logs {container_name}"
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, shell=True)
        return keyword in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def test_dlm_normal_flow(leader_port: int):
    print("\n" + "="*70)
    print("1. UJI DISTRIBUTED LOCK MANAGER (DLM) - KONSISTENSI & DEADLOCK")
    print("="*70)

    url_acquire = f"http://localhost:{leader_port}/lock/acquire"
    url_release = f"http://localhost:{leader_port}/lock/release"
    
    data_a = {"lock_name": "DB_RW", "client_id": "ClientA", "lock_type": "exclusive", "timeout": LOCK_TIMEOUT_SECS}
    data_b = {"lock_name": "DB_RW", "client_id": "ClientB", "lock_type": "exclusive", "timeout": 1.0}
    
    result_a = requests.post(url_acquire, headers=HEADERS, json=data_a).json()
    print(f"[1] Client A Acquire: Success={result_a.get('success')}")

    result_b = requests.post(url_acquire, headers=HEADERS, json=data_b).json()
    print(f"[2] Client B Contention: Success={result_b.get('success')}")
    assert result_a['success'] is True and result_b['success'] is False, "DLM Contention Test Failed"

    print(f"\n[3] Uji Deadlock: Menunggu {LOCK_TIMEOUT_SECS + 2} detik...")
    time.sleep(LOCK_TIMEOUT_SECS + 2)
    time.sleep(1)
    
    leader_container = f"docker-node_lock_{leader_port-8000}-1"
    deadlock_passed = check_log_for_event(leader_container, "DEADLOCK DETECTED")
    print(f"    Deadlock Log Check: {'✅ PASSED' if deadlock_passed else '❌ FAILED'}")

    final_result = requests.post(url_acquire, headers=HEADERS, json=data_b).json()
    
    if final_result.get('success') is True:
        print("✅ PASSED: Deadlock Detection BERHASIL. Lock dirilis dan diperoleh kembali.")
        requests.post(url_release, headers=HEADERS, json=data_b)
    else:
        print("❌ FAILED: Lock masih macet setelah Deadlock Detection.")

def test_queue_redelivery():
    print("\n" + "="*70)
    print("2. UJI DISTRIBUTED QUEUE - AT-LEAST-ONCE DELIVERY")
    print("="*70)
    
    queue_port = PORTS['queue']
    topic = "INVOICE_PROCESS"
    topic = f"INVOICE_PROCESS_{time.time()}"
    url_pub = f"http://localhost:{queue_port}/queue/publish"
    url_con = f"http://localhost:{queue_port}/queue/consume"
    url_ack = f"http://localhost:{queue_port}/queue/ack"

    requests.post(url_pub, headers=HEADERS, json={"topic": topic, "data": {"order_id": 102}})
    print(f"[1] Pesan dipublish.")

    msg_result_1 = requests.post(url_con, headers=HEADERS, json={"topic": topic}).json()
    
    if msg_result_1.get('status') == 'REDIRECT':
        print(f"❌ FAILED: Hashing merutekan {topic} ke node lain. Tes Queue dihentikan.")
        return 
        
    message_id = msg_result_1.get('message', {}).get('id')
        
    print(f"[2] Pesan dikonsumsi (ID: {message_id}). TIDAK ada ACK.")

    print(f"⏱️ Menunggu {REDELIVERY_WAIT_SECS} detik untuk Redelivery Monitor...")
    time.sleep(REDELIVERY_WAIT_SECS)

    msg_result_2 = requests.post(url_con, headers=HEADERS, json={"topic": topic}).json()
    
    if msg_result_2.get('message', {}).get('id') == message_id:
        print(f"✅ PASSED: At-Least-Once Delivery BERHASIL (Pesan ID {message_id} di-Redeliver).")

        requests.post(url_ack, headers=HEADERS, json={"topic": topic, "message_id": message_id})
    else:
        print("❌ FAILED: Redelivery Monitor tidak bekerja.")

def test_cache_mesi():
    print("\n" + "="*70)
    print("3. UJI DISTRIBUTED CACHE COHERENCE (MESI)")
    print("="*70)
    
    key = "USER_PROFILE_1"
    
    url_A_write = f"http://localhost:{PORTS['cache'][0]}/cache/write"
    url_B_read = f"http://localhost:{PORTS['cache'][1]}/cache/read"
    url_C_write = f"http://localhost:{PORTS['cache'][2]}/cache/write"
    
    requests.post(url_A_write, headers=HEADERS, json={"key": key, "value": "Version_1"})
    print("[1] Node A (8021) WRITE V1. (I -> M)")

    requests.post(url_B_read, headers=HEADERS, json={"key": key})
    print("[2] Node B (8022) READ. (I -> S)")

    requests.post(url_C_write, headers=HEADERS, json={"key": key, "value": "Version_2_New"})
    print("[3] Node C (8023) WRITE V2. (Memicu INVAL ke Node B)")

    time.sleep(1.0)

    container_b = f"docker-node_cache_{PORTS['cache'][1]-8000}-1"
    time.sleep(1)
    inval_passed = check_log_for_event(container_b, f"Received INVAL for {key}. State -> I")
    
    if inval_passed:
        print("✅ PASSED: MESI Invalidation BERHASIL. Node B log: Received INVAL.")
    else:
        print("❌ FAILED: Node B gagal menerima atau memproses INVAL.")


if __name__ == "__main__":
    
    leader_port = find_leader_port()
    
    if leader_port:
        test_dlm_normal_flow(leader_port)
        test_queue_redelivery()
        test_cache_mesi()
    else:
        print("\nERROR FATAL: Gagal memulai pengujian karena Leader Raft tidak ditemukan.")
        sys.exit(1)