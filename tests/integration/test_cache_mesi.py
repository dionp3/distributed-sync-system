import pytest
import requests
import time
import redis

REDIS_HOST = 'localhost' 
REDIS_PORT = 6379

# --- KONFIGURASI DOCKER ---
# Asumsi Cache Nodes berjalan di port host 8021, 8022, 8023
CACHE_URLS = {
    "node_A": "http://localhost:8021",
    "node_B": "http://localhost:8022",
    "node_C": "http://localhost:8023",
}
HEADERS = {"Content-Type": "application/json"}
TEST_KEY = "TestKey_MESI"

# --- FIXTURE KRITIS: Membersihkan Redis State ---
@pytest.fixture(scope="module", autouse=True)
def clean_redis():
    """Memastikan Redis bersih dari data test sebelumnya."""
    r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    r.flushdb()
    print("\n[SETUP] Redis flushed for MESI test.")
    # Yield untuk menjalankan test, lalu opsional cleanup
    yield
    # r.flushdb() # Opsional: membersihkan setelah semua test selesai

def get_cache_state(node_url):
    """Mengambil metrik dan mencoba mengekstrak state (tidak langsung, tapi untuk debugging)."""
    # Karena API utama tidak mengekspos state, kita andalkan logs atau API internal jika ada.
    # Di sini, kita asumsikan state bisa diverifikasi melalui logic API atau mock.
    # Dalam implementasi yang sebenarnya, kita harus memparsing log node atau membuat endpoint debug.
    
    # Untuk tes integrasi ini, kita akan mengandalkan ASSERT pada nilai yang seharusnya hilang/muncul.
    pass


def test_01_mesi_invalidation_flow():
    """Menguji alur W -> R -> W yang memicu Invalidasi (I -> M -> S -> I)."""
    
    # Node URLs
    url_A = CACHE_URLS["node_A"]
    url_B = CACHE_URLS["node_B"]
    url_C = CACHE_URLS["node_C"]

    # 1. Node A WRITE (I -> M): A menulis. Membroadcast INVAL.
    print("\n--- 1. Node A WRITE (I -> M) ---")
    resp = requests.post(f"{url_A}/cache/write", headers=HEADERS, json={"key": TEST_KEY, "value": "v1"})
    assert resp.json()['status'] == "WRITE_MISS_INVALIDATING" # Asumsi status ini saat I->M

    # 2. Node B READ (I -> S): B membaca. Miss, mengambil dari Memori Utama/Peer.
    print("--- 2. Node B READ (I -> S) ---")
    resp = requests.post(f"{url_B}/cache/read", headers=HEADERS, json={"key": TEST_KEY})
    assert resp.json()['status'] == "MISS_FETCHED"
    assert resp.json()['value'] == "v1"
    # State B sekarang Shared (S).

    # 3. Node C WRITE (Trigger Invalidation): C menulis. State A, B harus menjadi Invalid (I).
    print("--- 3. Node C WRITE (Trigger I -> M) ---")
    resp = requests.post(f"{url_C}/cache/write", headers=HEADERS, json={"key": TEST_KEY, "value": "v2"})
    assert resp.json()['status'] == "WRITE_MISS_INVALIDATING"
    
    # --- PERBAIKAN KRITIS: BERI WAKTU AGAR INVAL SELESAI DIPROSES ---
    # Di sistem async, RPC dan background task butuh waktu untuk dieksekusi.
    time.sleep(0.2) 
    
    # 4. Verifikasi (Implicitly via READ): Node B membaca lagi.
    print("--- 4. Node B READ ulang (Harus MISS) ---")
    resp = requests.post(f"{url_B}/cache/read", headers=HEADERS, json={"key": TEST_KEY})
    
    # Karena Node B seharusnya I -> MISS, ia akan mengambil v2 yang baru
    assert resp.json()['status'] == "MISS_FETCHED"
    assert resp.json()['value'] == "v2"
    
    # Verifikasi konsistensi
    # Jika Invalidasi gagal, Node B akan merespons dengan HIT v1 yang salah.
    # Karena Node B merespons MISS dan mengambil V2, Invalidasi S->I berhasil terjadi di latar belakang.