import pytest
import requests
import json
import time
import redis
from typing import Dict, Any, List

REDIS_HOST = 'localhost' 
REDIS_PORT = 6379

CACHE_URLS = {
    "node_A": "http://localhost:8021",
    "node_B": "http://localhost:8022",
    "node_C": "http://localhost:8023",
}
HEADERS = {"Content-Type": "application/json"}
TEST_KEY = "TestKey_MESI"

@pytest.fixture(scope="module", autouse=True)
def clean_redis():
    r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    r.flushdb()
    print("\n[SETUP] Redis flushed for MESI test.")
    # r.set(TEST_KEY, "initial_value") 
    yield

def test_01_mesi_invalidation_flow():
    url_A = CACHE_URLS["node_A"]
    url_B = CACHE_URLS["node_B"]
    url_C = CACHE_URLS["node_C"]

    print("\n--- 1. Node A WRITE (I -> M) ---")
    resp = requests.post(f"{url_A}/cache/write", headers=HEADERS, json={"key": TEST_KEY, "value": "v1"})
    assert resp.json()['status'] == "WRITE_MISS_INVALIDATING"

    print("--- 2. Node B READ (I -> S) ---")
    resp = requests.post(f"{url_B}/cache/read", headers=HEADERS, json={"key": TEST_KEY})
    assert resp.json()['status'] == "MISS_FETCHED"
    assert resp.json()['value'] == "v1"

    print("--- 3. Node C WRITE (Trigger I -> M) ---")
    resp = requests.post(f"{url_C}/cache/write", headers=HEADERS, json={"key": TEST_KEY, "value": "v2"})
    assert resp.json()['status'] == "WRITE_MISS_INVALIDATING"
    
    time.sleep(1.0) 
    
    print("--- 4. Node B READ ulang (Harus MISS dan mengambil V2 yang baru) ---")
    resp = requests.post(f"{url_B}/cache/read", headers=HEADERS, json={"key": TEST_KEY})
    
    assert resp.json()['status'] == "MISS_FETCHED"
    assert resp.json()['value'] == "v2"