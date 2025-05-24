import os
import json
import boto3
from datetime import datetime
import redis
from dotenv import load_dotenv
from config import QUEUE_NAME, QUEUE_URL, DLQ_URL
import logging
from sqlalchemy.orm import Session
from models import Todo, get_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Initialize Redis client
redis_host = os.getenv('REDIS_HOST')
redis_port = int(os.getenv('REDIS_PORT'))
redis_password = os.getenv('REDIS_PASSWORD')

logger.info(f"Initializing Redis client with host: {redis_host}, port: {redis_port}")

redis_client = redis.Redis(
    host=redis_host,
    port=redis_port,
    password=redis_password,
    ssl=False,  # Disable SSL
)

# Test Redis connection
try:
    redis_client.ping()
    logger.info("Successfully connected to Redis")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {str(e)}")
    raise

# Initialize SQS client
sqs_config = {
    'region_name': os.getenv('SQS_REGION'),
    'endpoint_url': os.getenv('SQS_QUEUE_URL')
}

# Only add AWS credentials for local development
if 'elasticmq' in sqs_config['endpoint_url']:
    sqs_config.update({
        'aws_access_key_id': os.getenv('SQS_ACCESS_KEY'),
        'aws_secret_access_key': os.getenv('SQS_SECRET_KEY')
    })

sqs = boto3.client('sqs', **sqs_config)

# Database operations
def get_all_todos(db: Session):
    logger.info("Fetching all todos from database")
    todos = db.query(Todo).all()
    logger.info(f"Found {len(todos)} todos in database")
    return todos

def get_todo_by_id(db: Session, todo_id: int):
    logger.info(f"Fetching todo with id {todo_id} from database")
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if todo:
        logger.info(f"Found todo {todo_id} in database")
    else:
        logger.info(f"Todo {todo_id} not found in database")
    return todo

def create_todo(db: Session, todo_data: dict):
    logger.info("Creating new todo in database")
    todo = Todo(**todo_data)
    db.add(todo)
    db.commit()
    db.refresh(todo)
    logger.info(f"Created todo with id {todo.id} in database")
    return todo

def update_todo(db: Session, todo_id: int, todo_data: dict):
    logger.info(f"Updating todo {todo_id} in database")
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if todo:
        for key, value in todo_data.items():
            setattr(todo, key, value)
        db.commit()
        db.refresh(todo)
        logger.info(f"Updated todo {todo_id} in database")
        return todo
    logger.info(f"Todo {todo_id} not found in database for update")
    return None

def delete_todo(db: Session, todo_id: int):
    logger.info(f"Deleting todo {todo_id} from database")
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if todo:
        db.delete(todo)
        db.commit()
        logger.info(f"Deleted todo {todo_id} from database")
        return True
    logger.info(f"Todo {todo_id} not found in database for deletion")
    return False

# Cache operations
def get_cached_todos():
    logger.info("Fetching todos from Redis cache")
    cached_data = redis_client.get('all_todos')
    if cached_data:
        logger.info("Found todos in Redis cache")
        return json.loads(cached_data)
    logger.info("No todos found in Redis cache")
    return None

def get_cached_todo(todo_id: int):
    logger.info(f"Fetching todo {todo_id} from Redis cache")
    cached_data = redis_client.get(f'todo:{todo_id}')
    if cached_data:
        logger.info(f"Found todo {todo_id} in Redis cache")
        return json.loads(cached_data)
    logger.info(f"Todo {todo_id} not found in Redis cache")
    return None

# Health check functions
def check_postgres():
    try:
        db = next(get_db())
        version = db.execute("SELECT version()").scalar()
        db.close()
        logger.info("PostgreSQL health check passed")
        return {'status': 'healthy', 'version': version}
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {str(e)}")
        return {'status': 'unhealthy', 'error': str(e)}

def check_redis():
    try:
        redis_client.ping()
        test_key = 'health_check_test'
        redis_client.set(test_key, 'ok')
        value = redis_client.get(test_key)
        redis_client.delete(test_key)
        if value != b'ok':
            raise Exception('Redis set/get test failed')
        logger.info("Redis health check passed")
        return {'status': 'healthy', 'version': redis_client.info()['redis_version']}
    except Exception as e:
        logger.error(f"Redis health check failed: {str(e)}")
        return {'status': 'unhealthy', 'error': str(e)}

def check_elasticmq():
    try:
        response = sqs.list_queues()
        queues = response.get('QueueUrls', [])
        queue_exists = any(QUEUE_NAME in q for q in queues)
        if not queue_exists:
            logger.error(f"Required queue {QUEUE_NAME} not found")
            return {'status': 'unhealthy', 'error': f'Required queue {QUEUE_NAME} not found'}
        logger.info("ElasticMQ health check passed")
        return {'status': 'healthy', 'queues': len(queues)}
    except Exception as e:
        logger.error(f"ElasticMQ health check failed: {str(e)}")
        return {'status': 'unhealthy', 'error': str(e)}

def send_notification(todo_id, action, todo_data=None):
    """Send a notification to SQS queue"""
    try:
        message = {
            'todo_id': todo_id,
            'action': action,
            'timestamp': datetime.utcnow().isoformat()
        }

        if todo_data:
            # Ensure todo_data is a dictionary
            if not isinstance(todo_data, dict):
                logger.error(f"todo_data must be a dictionary, got {type(todo_data)}")
                return None

            # Log the todo_data before adding it to the message
            logger.info(f"Adding todo_data to message: {todo_data}")
            message.update(todo_data)

        # Log the final message before sending
        logger.info(f"Sending message to SQS: {message}")

        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message)
        )
        logger.info(f"Notification sent successfully: {message}")
        return response
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        return None

def update_cache(todo_id, todo_data):
    """Update Redis cache with todo data"""
    try:
        redis_client.set(f"todo:{todo_id}", json.dumps(todo_data))
        logger.info(f"Cache updated for todo {todo_id}")
    except Exception as e:
        logger.error(f"Error updating cache: {e}")

def get_from_cache(todo_id):
    """Get todo data from Redis cache"""
    try:
        data = redis_client.get(f"todo:{todo_id}")
        return json.loads(data) if data else None
    except Exception as e:
        logger.error(f"Error getting from cache: {e}")
        return None

def delete_from_cache(todo_id):
    """Delete todo data from Redis cache"""
    try:
        redis_client.delete(f"todo:{todo_id}")
        logger.info(f"Cache deleted for todo {todo_id}")
    except Exception as e:
        logger.error(f"Error deleting from cache: {e}")
