from locust import HttpUser, task, between
import random

LEADER_PORT = 8001 
QUEUE_PORT = 8011
CACHE_PORT = 8021

class DistributedSystemUser(HttpUser):
    wait_time = between(0.1, 0.5) 
    host = "http://localhost" 

    def on_start(self):
        self.client_id = f"User_{random.randint(1000, 9999)}"

    # 1. Tes Distributed Lock Manager (Raft)
    @task(3) 
    def test_lock_acquire_release(self):
        lock_name = f"res_{random.randint(1, 10)}"
        
        # Acquire Lock
        self.client.post(f":{LEADER_PORT}/lock/acquire", 
                         json={"lock_name": lock_name, "client_id": self.client_id}, 
                         name="/Lock/Acquire")
        
        # Release Lock
        self.client.post(f":{LEADER_PORT}/lock/release", 
                         json={"lock_name": lock_name, "client_id": self.client_id}, 
                         name="/Lock/Release")

    # 2. Tes Distributed Queue (At-Least-Once)
    @task(2)
    def test_queue_publish_consume(self):
        topic_name = f"topic_{random.choice(['A', 'B', 'C'])}"

        # Publish Pesan
        self.client.post(f":{QUEUE_PORT}/queue/publish", 
                         json={"topic": topic_name, "data": {"key": "value"}}, 
                         name="/Queue/Publish")
        
        # Consume Pesan
        self.client.post(f":{QUEUE_PORT}/queue/consume", 
                         json={"topic": topic_name}, 
                         name="/Queue/Consume")

    # 3. Tes Distributed Cache (Read/Write)
    @task(1)
    def test_cache_read_write(self):
        cache_key = f"data_{random.randint(1, 1000)}"
        
        # Cache Read
        self.client.post(f":{CACHE_PORT}/cache/read", 
                         json={"key": cache_key}, 
                         name="/Cache/Read")
        
        # Cache Write
        self.client.post(f":{CACHE_PORT}/cache/write", 
                         json={"key": cache_key, "value": "new_data"}, 
                         name="/Cache/Write")