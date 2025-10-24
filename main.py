import asyncio
import os
import sys
import json
import uuid
import time
from aiohttp import web
from dotenv import load_dotenv
from typing import Dict, Any, List

from src.communication.message_passing import NodeCommunication
from src.consensus.raft import RaftNode, RaftState
from src.nodes.lock_manager import DistributedLockManager
from src.nodes.queue_node import ConsistentHashRing, DistributedQueueNode
from src.nodes.cache_node import DistributedCacheNode, CacheState

load_dotenv()

COMM = None
RAFT_NODE = None
LOCK_MANAGER = None
QUEUE_NODE = None
CACHE_NODE = None

def format_prometheus(metrics_dict: dict) -> str:
    output = "# HELP distributed_sync_metrics Metrics from the node\n"
    output += "# TYPE distributed_sync_metrics gauge\n"
    
    labeled_metrics = {}
    
    for key, value in metrics_dict.items():
        if key in ('node_id', 'state', 'status', 'is_leader'):
            labeled_metrics[key] = str(value)
            continue
        
        if isinstance(value, (int, float)):
            output += f"{key} {value}\n"
    
    node_id = labeled_metrics.get("node_id", "unknown")

    if 'state' in labeled_metrics:
        output += f'raft_state_info{{node_id="{node_id}", raft_state="{labeled_metrics["state"]}"}} 1\n'
    if 'is_leader' in labeled_metrics:
        output += f'raft_is_leader {1 if labeled_metrics["is_leader"] == "True" else 0}\n'
    if 'status' in labeled_metrics:
        output += f'queue_node_status{{node_id="{node_id}", node_status="{labeled_metrics["status"]}"}} 1\n'
        
    return output.strip()

def get_port_from_id(node_id: str, base_port: int) -> int:
    try:
        return base_port + int(node_id.split('_')[-1])
    except:
        return base_port + 1

def safe_json_load(env_var_name: str, default_val: Any = "{}"):
    val = os.getenv(env_var_name)
    if not val:
        return json.loads(default_val)
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        print(f"FATAL ERROR: Environment variable {env_var_name} has invalid JSON format: {val}")
        sys.exit(1)


async def create_raft_routes(raft: RaftNode, lock_mgr: DistributedLockManager):
    routes = web.RouteTableDef()

    @routes.post('/raft/request_vote')
    async def request_vote(request):
        data = await request.json()
        response = await raft.handle_request_vote(data)
        return web.json_response(response)

    @routes.post('/raft/append_entries')
    async def append_entries(request):
        data = await request.json()
        response = await raft.handle_append_entries(data)
        return web.json_response(response)

    @routes.post('/lock/acquire')
    async def acquire_lock_handler(request):
        data = await request.json()
        client_id = data.get('client_id', str(uuid.uuid4()))
        response = await lock_mgr.acquire_lock(
            lock_name=data['lock_name'],
            lock_type=data.get('lock_type', 'exclusive'),
            client_id=client_id,
            timeout=data.get('timeout', 10.0)
        )
        return web.json_response(response)
        
    @routes.post('/lock/release')
    async def release_lock_handler(request):
        data = await request.json()
        response = await lock_mgr.release_lock(data['lock_name'], data['client_id'])
        return web.json_response(response)

    @routes.get('/metrics')
    async def get_lock_metrics(request):
        metrics = {
            'node_id': raft.node_id, 
            'state': raft.state.value,
            'term': raft.current_term,
            'commit_index': raft.commit_index,
            'is_leader': str(raft.state == RaftState.LEADER)
        }
        return web.Response(text=format_prometheus(metrics), content_type="text/plain; version=0.0.4")

    return routes

async def create_queue_routes(queue: DistributedQueueNode):
    routes = web.RouteTableDef()

    @routes.post('/queue/publish')
    async def publish_handler(request):
        data = await request.json()
        response = await queue.publish(data['topic'], data['data'])
        return web.json_response(response)

    @routes.post('/queue/consume')
    async def consume_handler(request):
        data = await request.json()
        response = await queue.consume(data['topic'])
        return web.json_response(response)

    @routes.post('/queue/ack')
    async def acknowledge_handler(request):
        data = await request.json()
        response = await queue.acknowledge(data['topic'], data['message_id'])
        return web.json_response(response)
        
    @routes.get('/metrics')
    async def get_queue_metrics(request):
        metrics = {'node_id': queue.node_id, 'status': 'ready'}
        return web.Response(text=format_prometheus(metrics), content_type="text/plain; version=0.0.4")
        
    return routes

async def create_cache_routes(cache: DistributedCacheNode):
    routes = web.RouteTableDef()
    
    @routes.post('/cache/read')
    async def read_handler(request):
        data = await request.json()
        response = await cache.read(data['key'])
        return web.json_response(response)

    @routes.post('/cache/write')
    async def write_handler(request):
        data = await request.json()
        response = await cache.write(data['key'], data['value'])
        return web.json_response(response)

    @routes.post('/cache/invalidate')
    async def invalidate_handler(request):
        data = await request.json()
        cache.handle_invalidation(data['key'])
        return web.json_response({"success": True})
        
    @routes.get('/metrics')
    async def get_cache_metrics(request):
        metrics = cache.get_metrics()
        return web.Response(text=format_prometheus(metrics), content_type="text/plain; version=0.0.4")

    return routes


async def init_app():
    global COMM, RAFT_NODE, LOCK_MANAGER, QUEUE_NODE, CACHE_NODE
    
    app = web.Application()
    NODE_ID = os.getenv("NODE_ID")
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    NODE_TYPE = os.getenv("NODE_TYPE")

    if NODE_TYPE == 'lock':
        PEERS = safe_json_load("RAFT_PEERS")
        COMM = NodeCommunication(NODE_ID, PEERS)
        LOCK_MANAGER = DistributedLockManager(None) 
        RAFT_NODE = RaftNode(NODE_ID, list(PEERS.keys()), COMM, LOCK_MANAGER)
        LOCK_MANAGER.raft_node = RAFT_NODE
        app.add_routes(await create_raft_routes(RAFT_NODE, LOCK_MANAGER))
        asyncio.create_task(RAFT_NODE.start())
        asyncio.create_task(LOCK_MANAGER.deadlock_monitor())
        print(f"Running Lock Node: {NODE_ID}")

    elif NODE_TYPE == 'queue':
        QUEUE_NODES = safe_json_load("QUEUE_NODES", default_val="[]")
        ring = ConsistentHashRing(QUEUE_NODES)
        QUEUE_NODE = DistributedQueueNode(NODE_ID, ring, REDIS_HOST)
        app.add_routes(await create_queue_routes(QUEUE_NODE))
        asyncio.create_task(QUEUE_NODE.redelivery_monitor())
        print(f"Running Queue Node: {NODE_ID}")
        
    elif NODE_TYPE == 'cache':
        CACHE_PEERS = safe_json_load("CACHE_PEERS")
        COMM = NodeCommunication(NODE_ID, CACHE_PEERS)
        CACHE_NODE = DistributedCacheNode(NODE_ID, int(os.getenv("CACHE_MAX_SIZE", 100)), COMM)
        app.add_routes(await create_cache_routes(CACHE_NODE))
        print(f"Running Cache Node: {NODE_ID}")

    return app

if __name__ == '__main__':
    node_type = os.getenv("NODE_TYPE")
    
    if node_type == 'lock':
        port = get_port_from_id(os.getenv("NODE_ID"), 8000)
    elif node_type == 'queue':
        port = get_port_from_id(os.getenv("NODE_ID"), 8010)
    elif node_type == 'cache':
        port = get_port_from_id(os.getenv("NODE_ID"), 8020)
    else:
        print("Error: NODE_TYPE environment variable is not set correctly. Exiting.")
        sys.exit(1)

    web.run_app(init_app(), host='0.0.0.0', port=port)