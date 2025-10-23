import pytest
import time
from unittest.mock import MagicMock
from src.consensus.raft import RaftNode 
from src.communication.message_passing import NodeCommunication

# Mocking dependensi eksternal untuk pengujian unit
@pytest.fixture
def mock_raft_node():
    """Membuat instance RaftNode dengan dependensi yang di-mock."""
    peers = ['n2', 'n3']
    comm = MagicMock(spec=NodeCommunication)
    lock_manager = MagicMock()
    node = RaftNode('n1', peers, comm, lock_manager)
    node.log = [(1, 'cmd1'), (1, 'cmd2'), (2, 'cmd3')] # Log sampel: Index 1, 2, 3
    node.current_term = 2
    return node

def test_get_random_timeout_range(mock_raft_node):
    """Menguji apakah timeout berada dalam rentang yang ditentukan."""
    timeout = mock_raft_node._get_random_timeout()
    assert mock_raft_node.election_timeout_min <= timeout <= mock_raft_node.election_timeout_max

def test_log_is_at_least_up_to_date_term_check(mock_raft_node):
    """Uji jika term lebih besar, dianggap up-to-date."""
    
    # Skenario 1: Candidate log term lebih besar (Harus True)
    # Log saat ini: term=2, index=3. Candidate: term=3, index=1.
    assert mock_raft_node._log_is_at_least_up_to_date(candidate_last_index=1, candidate_last_term=3) is True
    
    # Skenario 2: Candidate log term lebih kecil (Harus False)
    # Log saat ini: term=2, index=3. Candidate: term=1, index=5.
    assert mock_raft_node._log_is_at_least_up_to_date(candidate_last_index=5, candidate_last_term=1) is False

def test_log_is_at_least_up_to_date_length_check(mock_raft_node):
    """Uji jika term sama, log yang lebih panjang menang."""
    
    # Skenario 3: Term sama, Candidate log lebih panjang (Harus True)
    # Log saat ini: term=2, index=3. Candidate: term=2, index=5.
    assert mock_raft_node._log_is_at_least_up_to_date(candidate_last_index=5, candidate_last_term=2) is True
    
    # Skenario 4: Term sama, Candidate log lebih pendek (Harus False)
    # Log saat ini: term=2, index=3. Candidate: term=2, index=1.
    assert mock_raft_node._log_is_at_least_up_to_date(candidate_last_index=1, candidate_last_term=2) is False