import pytest
import time
from unittest.mock import MagicMock
from src.nodes.lock_manager import DistributedLockManager
from src.consensus.raft import RaftNode

@pytest.fixture
def mock_lock_manager():
    raft_mock = MagicMock(spec=RaftNode)
    RaftStateMock = type('RaftStateMock', (object,), {'LEADER': 'leader'})
    raft_mock.state = RaftStateMock.LEADER
    
    lock_manager = DistributedLockManager(raft_mock)
    return lock_manager

@pytest.mark.asyncio
async def test_deadlock_monitor_triggers_release(mock_lock_manager):
    expired_time = time.time() - 5
    mock_lock_manager.locks["EXPIRED_LOCK"] = {
        "type": "exclusive", 
        "holders": ["Client_X"], 
        "expiry": expired_time
    }
    
    await mock_lock_manager.deadlock_monitor()
    
    mock_lock_manager.raft_node.submit_command.assert_called_once()
    
    args, _ = mock_lock_manager.raft_node.submit_command.call_args
    command = args[0]
    
    assert command['type'] == 'RELEASE'
    assert command['lock_name'] == 'EXPIRED_LOCK'
    assert command['client_id'] == 'SYSTEM_TIMEOUT'

@pytest.mark.asyncio
async def test_deadlock_monitor_ignores_valid_lock(mock_lock_manager):
    valid_time = time.time() + 5 
    mock_lock_manager.locks["VALID_LOCK"] = {
        "type": "exclusive", 
        "holders": ["Client_Y"], 
        "expiry": valid_time
    }
    
    await mock_lock_manager.deadlock_monitor()
    
    mock_lock_manager.raft_node.submit_command.assert_not_called()