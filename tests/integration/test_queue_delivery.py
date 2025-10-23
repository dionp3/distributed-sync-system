import pytest
import asyncio
import time
import redis
from src.nodes.queue_node import DistributedQueueNode, ConsistentHashRing
from typing import List, Dict, Any, Optional

QUEUE_NODES: List[str] = ["q1"]
TEST_RING = ConsistentHashRing(QUEUE_NODES)

@pytest.fixture
def queue_node():
    node = DistributedQueueNode("q1", TEST_RING, redis_host='localhost')
    node.redis_conn.flushdb()
    return node

@pytest.mark.asyncio
async def test_publish_consume_success(queue_node: DistributedQueueNode):
    topic = "basic_topic"
    
    pub_result = await queue_node.publish(topic, {"data": "test_message"})
    assert pub_result['status'] == "SUCCESS"
    
    consume_result = await queue_node.consume(topic)
    assert consume_result['status'] == "MESSAGE_SENT"
    
    ack_result = await queue_node.acknowledge(topic, consume_result['message']['id'])
    assert ack_result['status'] == "ACK_RECEIVED"
    
    pending_meta_key = f"{queue_node.PENDING_PREFIX}{topic}{queue_node.META_SUFFIX}"
    assert queue_node.redis_conn.hlen(pending_meta_key) == 0

@pytest.mark.asyncio
async def test_at_least_once_redelivery(queue_node: DistributedQueueNode):
    topic = "redeliver_topic"
    
    await queue_node.publish(topic, {"data": "lost_message"})
    
    consume_result = await queue_node.consume(topic)
    message_id = consume_result['message']['id']
    
    pending_meta_key = f"{queue_node.PENDING_PREFIX}{topic}{queue_node.META_SUFFIX}"
    assert queue_node.redis_conn.hget(pending_meta_key, message_id) is not None
    
    await asyncio.sleep(queue_node.REDELIVERY_TIMEOUT + 1)
    
    await queue_node.redelivery_monitor()
    
    re_consume_result = await queue_node.consume(topic)
    assert re_consume_result['status'] == "MESSAGE_SENT"
    assert re_consume_result['message']['id'] == message_id
    
    await queue_node.acknowledge(topic, message_id)