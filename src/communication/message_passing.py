import aiohttp
import asyncio
import json
from typing import Dict, Any

class NodeCommunication:
    """Class untuk menangani RPC antar-node."""
    def __init__(self, node_id: str, peers: Dict[str, str]):
        self.node_id = node_id
        # peers: {'node_id': 'http://host:port'}
        self.peers = peers
        self.session = aiohttp.ClientSession()

    async def send_rpc(self, target_id: str, endpoint: str, payload: Dict[str, Any]):
        """Mengirim Request/Reply RPC (Raft-style, Cache Invalidation)."""
        if target_id not in self.peers:
            return {'success': False, 'error': 'Peer not found'}
        
        url = f"{self.peers[target_id]}{endpoint}"
        
        try:
            # Gunakan timeout yang ketat untuk RPC cepat
            async with self.session.post(url, json=payload, timeout=0.5) as response: 
                if response.status == 200:
                    return await response.json()
                else:
                    return {'success': False, 'error': f'HTTP Error {response.status}'}
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # Handle kegagalan network/timeout
            return {'success': False, 'error': str(e)}

    async def broadcast_rpc(self, endpoint: str, payload: Dict[str, Any], exclude_self=True):
        """Broadcast pesan ke semua peer (misalnya, Heartbeat atau Invalidate Cache)."""
        tasks = []
        target_ids = []
        for peer_id in self.peers:
            if exclude_self and peer_id == self.node_id:
                continue
            tasks.append(self.send_rpc(peer_id, endpoint, payload))
            target_ids.append(peer_id)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return dict(zip(target_ids, results))

    async def close(self):
        await self.session.close()