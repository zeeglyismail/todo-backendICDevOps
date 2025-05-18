import pytest
from app import app
import json
from datetime import datetime, timedelta

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_check(client):
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'services' in data
    assert 'postgres' in data['services']
    assert 'redis' in data['services']
    assert 'elasticmq' in data['services']

def test_get_todos_empty(client):
    response = client.get('/todos')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)
    assert len(data) == 0

def test_create_todo(client):
    todo_data = {
        'title': 'Test Todo',
        'description': 'Test Description',
        'completed': False,
        'due_date': (datetime.utcnow() + timedelta(days=1)).isoformat()
    }
    response = client.post('/todos',
                          data=json.dumps(todo_data),
                          content_type='application/json')
    assert response.status_code == 202
    data = json.loads(response.data)
    assert 'todo_id' in data
    assert 'message' in data
    assert data['message'] == 'Todo creation has been queued'

def test_get_todo_not_found(client):
    response = client.get('/todos/999999')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'Todo not found'

def test_update_todo(client):
    # First create a todo
    todo_data = {
        'title': 'Test Todo',
        'description': 'Test Description',
        'completed': False
    }
    create_response = client.post('/todos',
                                data=json.dumps(todo_data),
                                content_type='application/json')
    todo_id = json.loads(create_response.data)['todo_id']

    # Then update it
    update_data = {
        'title': 'Updated Todo',
        'completed': True
    }
    response = client.put(f'/todos/{todo_id}',
                         data=json.dumps(update_data),
                         content_type='application/json')
    assert response.status_code == 202
    data = json.loads(response.data)
    assert 'message' in data
    assert data['message'] == 'Todo update has been queued'

def test_delete_todo(client):
    # First create a todo
    todo_data = {
        'title': 'Test Todo',
        'description': 'Test Description',
        'completed': False
    }
    create_response = client.post('/todos',
                                data=json.dumps(todo_data),
                                content_type='application/json')
    todo_id = json.loads(create_response.data)['todo_id']

    # Then delete it
    response = client.delete(f'/todos/{todo_id}')
    assert response.status_code == 202
    data = json.loads(response.data)
    assert 'message' in data
    assert data['message'] == 'Todo deletion has been queued'

def test_invalid_json(client):
    response = client.post('/todos',
                          data='invalid json',
                          content_type='application/json')
    assert response.status_code == 500
    data = json.loads(response.data)
    assert 'error' in data

def test_missing_required_fields(client):
    todo_data = {
        'description': 'Test Description',
        'completed': False
    }
    response = client.post('/todos',
                          data=json.dumps(todo_data),
                          content_type='application/json')
    assert response.status_code == 500
    data = json.loads(response.data)
    assert 'error' in data
