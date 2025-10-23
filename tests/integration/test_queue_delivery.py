import pytest
import time
import asyncio
from src.nodes.queue_node import DistributedQueueNode, ConsistentHashRing

# Definisikan node dan ring untuk pengujian
QUEUE_NODES = ["q1"] 
TEST_RING = ConsistentHashRing(QUEUE_NODES)

# Pytest fixture untuk inisialisasi DistributedQueueNode (terhubung ke Redis)
@pytest.fixture
def queue_node():
    # Asumsi Redis berjalan di host 'redis' (sesuai docker-compose)
    node = DistributedQueueNode("q1", TEST_RING, redis_host='localhost') # Gunakan localhost jika test dari host
    node.redis_conn.flushdb() # Bersihkan Redis sebelum tes
    return node

@pytest.mark.asyncio
async def test_publish_consume_success(queue_node):
    """Menguji publish dan consume dasar."""
    topic = "basic_topic"
    
    # Publish
    pub_result = await queue_node.publish(topic, {"data": "test_message"})
    assert pub_result['status'] == "SUCCESS"
    
    # Consume
    consume_result = await queue_node.consume(topic)
    assert consume_result['status'] == "MESSAGE_SENT"
    
    # ACK
    ack_result = await queue_node.acknowledge(topic, consume_result['message']['id'])
    assert ack_result['status'] == "ACK_RECEIVED"
    
    # Cek apakah antrian pending kosong
    pending_meta_key = f"{queue_node.PENDING_PREFIX}{topic}{queue_node.META_SUFFIX}"
    assert queue_node.redis_conn.hlen(pending_meta_key) == 0

@pytest.mark.asyncio
async def test_at_least_once_redelivery(queue_node):
    """Menguji skenario kegagalan ACK yang memicu redelivery."""
    topic = "redeliver_topic"
    
    # Publish
    await queue_node.publish(topic, {"data": "lost_message"})
    
    # Consume (Tanpa ACK)
    consume_result = await queue_node.consume(topic)
    message_id = consume_result['message']['id']
    
    # 1. Verifikasi pesan ada di antrian pending
    pending_meta_key = f"{queue_node.PENDING_PREFIX}{topic}{queue_node.META_SUFFIX}"
    assert queue_node.redis_conn.hget(pending_meta_key, message_id) is not None
    
    # 2. Simulasikan waktu berlalu (melebihi REDELIVERY_TIMEOUT=30s)
    # Karena test ini harus cepat, kita paksa monitor berjalan dan berharap Redis timeout (tidak ideal)
    # Atau, ubah REDELIVERY_TIMEOUT di node_queue.py menjadi nilai kecil (misal 1s) untuk pengujian.
    
    # Untuk lingkungan nyata, kita tunggu. Di sini, kita asumsikan REDELIVERY_TIMEOUT di set ke 1s atau 2s di code Anda.
    await asyncio.sleep(queue_node.REDELIVERY_TIMEOUT + 1)
    
    # 3. Jalankan monitor secara manual (Biasanya dijalankan oleh background task)
    await queue_node.redelivery_monitor()
    
    # 4. Verifikasi redelivery sukses (Pesan harus kembali ke antrian utama)
    re_consume_result = await queue_node.consume(topic)
    assert re_consume_result['status'] == "MESSAGE_SENT"
    assert re_consume_result['message']['id'] == message_id
    
    # Cleanup
    await queue_node.acknowledge(topic, message_id)