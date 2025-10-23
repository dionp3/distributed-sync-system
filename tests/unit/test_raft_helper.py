import pytest
from unittest.mock import MagicMock
from src.consensus.raft import RaftNode 
from src.communication.message_passing import NodeCommunication

@pytest.fixture
def mock_raft_node():
    peers = ['n2', 'n3']
    comm = MagicMock(spec=NodeCommunication)
    lock_manager = MagicMock()
    node = RaftNode('n1', peers, comm, lock_manager)
    node.log = [(1, 'cmd1'), (1, 'cmd2'), (2, 'cmd3')]
    node.current_term = 2
    return node

def test_get_random_timeout_range(mock_raft_node):
    timeout = mock_raft_node._get_random_timeout()
    assert mock_raft_node.election_timeout_min <= timeout <= mock_raft_node.election_timeout_max

def test_log_is_at_least_up_to_date_term_check(mock_raft_node):
    assert mock_raft_node._log_is_at_least_up_to_date(candidate_last_index=1, candidate_last_term=3) is True
    
    assert mock_raft_node._log_is_at_least_up_to_date(candidate_last_index=5, candidate_last_term=1) is False

def test_log_is_at_least_up_to_date_length_check(mock_raft_node):
    assert mock_raft_node._log_is_at_least_up_to_date(candidate_last_index=5, candidate_last_term=2) is True
    
    assert mock_raft_node._log_is_at_least_up_to_date(candidate_last_index=1, candidate_last_term=2) is False