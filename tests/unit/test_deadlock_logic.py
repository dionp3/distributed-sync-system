import pytest
import time
from unittest.mock import MagicMock
from src.nodes.lock_manager import DistributedLockManager
from src.consensus.raft import RaftNode # Menggunakan RaftNode yang sudah lengkap

@pytest.fixture
def mock_lock_manager():
    """Membuat instance Lock Manager dengan Raft yang di-mock."""
    raft_mock = MagicMock(spec=RaftNode)
    # Set status Leader agar monitor berjalan
    raft_mock.state = type('RaftStateMock', (object,), {'LEADER': 'leader'}) # Mock Enum LEADER
    raft_mock.state = raft_mock.state.LEADER 
    
    lock_manager = DistributedLockManager(raft_mock)
    return lock_manager

@pytest.mark.asyncio
async def test_deadlock_monitor_triggers_release(mock_lock_manager):
    """Menguji monitor mendeteksi lock yang expired dan mengirim command RELEASE."""
    
    # 1. Atur Lock yang expired
    expired_time = time.time() - 5 # 5 detik di masa lalu
    mock_lock_manager.locks["EXPIRED_LOCK"] = {
        "type": "exclusive", 
        "holders": ["Client_X"], 
        "expiry": expired_time
    }
    
    # 2. Jalankan monitor sekali
    await mock_lock_manager.deadlock_monitor()
    
    # 3. Verifikasi submit_command dipanggil
    # Monitor harus memanggil submit_command dengan command RELEASE
    mock_lock_manager.raft_node.submit_command.assert_called_once()
    
    # Verifikasi isi command yang dikirim
    args, kwargs = mock_lock_manager.raft_node.submit_command.call_args
    command = args[0]
    
    assert command['type'] == 'RELEASE'
    assert command['lock_name'] == 'EXPIRED_LOCK'
    assert command['client_id'] == 'SYSTEM_TIMEOUT'

@pytest.mark.asyncio
async def test_deadlock_monitor_ignores_valid_lock(mock_lock_manager):
    """Menguji monitor mengabaikan lock yang masih valid."""
    
    # 1. Atur Lock yang valid (5 detik di masa depan)
    valid_time = time.time() + 5 
    mock_lock_manager.locks["VALID_LOCK"] = {
        "type": "exclusive", 
        "holders": ["Client_Y"], 
        "expiry": valid_time
    }
    
    # 2. Jalankan monitor
    await mock_lock_manager.deadlock_monitor()
    
    # 3. Verifikasi submit_command TIDAK dipanggil
    mock_lock_manager.raft_node.submit_command.assert_not_called()