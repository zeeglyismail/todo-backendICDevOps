from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime
import logging
from config import initialize_services
from util import (
    get_all_todos, get_todo_by_id, create_todo, update_todo, delete_todo,
    get_cached_todos, get_cached_todo,
    check_postgres, check_redis, check_elasticmq, send_notification
)
from models import get_db, Todo

# Initialize services before creating the Flask app
initialize_services()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Enable debug mode
app.debug = True

# Add request logging middleware
@app.before_request
def log_request_info():
    logger.info('Request: %s %s - Headers: %s - Body: %s',
                request.method,
                request.url,
                dict(request.headers),
                request.get_data(as_text=True))

@app.after_request
def log_response_info(response):
    logger.info('Response: %s %s - Status: %s - Headers: %s - Body: %s',
                request.method,
                request.url,
                response.status,
                dict(response.headers),
                response.get_data(as_text=True))
    return response

@app.route('/_health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
    }), 200

@app.route('/health', methods=['GET'])
def health_check():
    postgres_status = check_postgres()
    redis_status = check_redis()
    elasticmq_status = check_elasticmq()

    status = {
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'postgres': postgres_status,
            'redis': redis_status,
            'elasticmq': elasticmq_status
        }
    }

    is_healthy = all(
        service['status'] == 'healthy'
        for service in status['services'].values()
    )

    return jsonify(status), 200 if is_healthy else 503

@app.route('/todos', methods=['GET'])
def get_todos():
    try:
        # Try to get todos from Redis cache
        cached_data = get_cached_todos()
        if cached_data:
            logger.info("Returning todos from cache")
            return jsonify(cached_data['todos']), 200

        # If not in cache, get from database
        db = next(get_db())
        todos = get_all_todos(db)

        logger.info("Returning todos from database")
        return jsonify([todo.to_dict() for todo in todos]), 200
    except Exception as e:
        logger.error(f"Error fetching todos: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/todos', methods=['POST'])
def create_todo_route():
    try:
        data = request.get_json()
        temp_id = int(datetime.utcnow().timestamp())
        send_notification(temp_id, 'todo_created', data)

        return jsonify({
            'message': 'Todo creation has been queued',
            'todo_id': temp_id
        }), 202
    except Exception as e:
        logger.error(f"Error creating todo: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/todos/<int:todo_id>', methods=['GET'])
def get_todo(todo_id):
    try:
        # Try to get todo from Redis cache
        cached_data = None
        try:
            cached_data = get_cached_todo(todo_id)
        except Exception as cache_exc:
            logger.warning(f"Cache error for todo {todo_id}: {str(cache_exc)}")
        if cached_data:
            logger.info(f"Returning todo {todo_id} from cache")
            return jsonify(cached_data), 200

        # If not in cache, get from database
        try:
            db = next(get_db())
            todo = get_todo_by_id(db, todo_id)
        except Exception as db_exc:
            logger.warning(f"DB error for todo {todo_id}: {str(db_exc)}")
            todo = None

        if todo:
            logger.info(f"Returning todo {todo_id} from database")
            return jsonify(todo.to_dict()), 200
        else:
            logger.info(f"Todo {todo_id} not found")
            return jsonify({'error': 'Todo not found'}), 404
    except Exception as e:
        logger.error(f"Unexpected error fetching todo {todo_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/todos/<int:todo_id>', methods=['PUT'])
def update_todo_route(todo_id):
    try:
        data = request.get_json()
        send_notification(todo_id, 'todo_updated', data)

        return jsonify({
            'message': 'Todo update has been queued',
            'todo_id': todo_id
        }), 202
    except Exception as e:
        logger.error(f"Error updating todo {todo_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/todos/<int:todo_id>', methods=['DELETE'])
def delete_todo_route(todo_id):
    try:
        db = next(get_db())
        todo = db.query(Todo).filter(Todo.id == int(todo_id)).first()
        if todo:
            db.delete(todo)
            db.commit()
        send_notification(todo_id, 'todo_deleted')

        return jsonify({
            'message': 'Todo deletion has been queued',
            'todo_id': todo_id
        }), 202
    except Exception as e:
        logger.error(f"Error deleting todo {todo_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001)
