import pytest
from worker import process_notification
import json
from datetime import datetime, timedelta

@pytest.fixture
def mock_db(mocker):
    mock_session = mocker.Mock()
    mock_session.query.return_value.filter.return_value.first.return_value = None
    mocker.patch('worker.get_db_session', return_value=mock_session)
    return mock_session

def test_process_todo_created(mock_db):
    todo_data = {
        'title': 'Test Todo',
        'description': 'Test Description',
        'completed': False,
        'due_date': (datetime.utcnow() + timedelta(days=1)).isoformat()
    }
    message = {
        'Body': json.dumps({
            'todo_id': 123,
            'action': 'todo_created',
            'todo_data': todo_data
        })
    }
    process_notification(message)
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once()

def test_process_todo_updated(mock_db):
    todo_data = {
        'title': 'Updated Todo',
        'completed': True
    }
    message = {
        'Body': json.dumps({
            'todo_id': 123,
            'action': 'todo_updated',
            'todo_data': todo_data
        })
    }
    process_notification(message)
    mock_db.commit.assert_called_once()

def test_process_todo_deleted(mock_db):
    message = {
        'Body': json.dumps({
            'todo_id': 123,
            'action': 'todo_deleted'
        })
    }
    process_notification(message)
    mock_db.commit.assert_called_once()

def test_process_invalid_message():
    message = {
        'Body': 'invalid json'
    }
    with pytest.raises(Exception):
        process_notification(message)

def test_process_missing_action():
    message = {
        'Body': json.dumps({
            'todo_id': 123
        })
    }
    with pytest.raises(Exception):
        process_notification(message)

def test_process_invalid_action():
    message = {
        'Body': json.dumps({
            'todo_id': 123,
            'action': 'invalid_action'
        })
    }
    with pytest.raises(Exception):
        process_notification(message)

def test_process_missing_todo_id():
    message = {
        'Body': json.dumps({
            'action': 'todo_created',
            'todo_data': {'title': 'Test Todo'}
        })
    }
    with pytest.raises(Exception):
        process_notification(message)
