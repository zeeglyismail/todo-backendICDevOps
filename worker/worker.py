import os
import json
import time
import boto3
import redis
from datetime import datetime
from dotenv import load_dotenv
import sys

from config import (
    QUEUE_URL, DATABASE_URL, REDIS_HOST, REDIS_PORT,SQS_REGION
)
from models import Todo, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Initialize Redis client
logger.info(f"Initializing Redis client with host: {REDIS_HOST}, port: {REDIS_PORT}")

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=os.getenv('REDIS_PASSWORD'),
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
    'region_name': SQS_REGION,
}

# Only add endpoint URL and credentials for local development
if 'elasticmq' in QUEUE_URL:
    sqs_config.update({
        'endpoint_url': QUEUE_URL,
        'aws_access_key_id': os.getenv('SQS_ACCESS_KEY'),
        'aws_secret_access_key': os.getenv('SQS_SECRET_KEY')
    })

sqs = boto3.client('sqs', **sqs_config)

def get_db_session():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    return Session()

def init_db():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)

def retry_on_error(max_retries=3, delay=1):
    """Decorator to retry operations on failure"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

def todo_to_dict(todo):
    """Convert a Todo object to a dictionary with proper datetime formatting"""
    return {
        'id': todo.id,
        'title': todo.title,
        'description': todo.description,
        'due_date': todo.due_date.isoformat() if todo.due_date else None,
        'priority': todo.priority,
        'status': todo.status,
        'created_at': todo.created_at.isoformat() if todo.created_at else None,
        'updated_at': todo.updated_at.isoformat() if todo.updated_at else None
    }

@retry_on_error(max_retries=3)
def update_all_todos_cache(session):
    """Update the all_todos cache with fresh data from database"""
    try:
        invalidate_all_todos_cache()
        # Get fresh data from database
        todos = session.query(Todo).all()
        todos_list = [todo_to_dict(todo) for todo in todos]

        # Update cache with new data
        cache_data = {
            'todos': todos_list,
            '_cached_at': datetime.utcnow().isoformat()
        }
        redis_client.set('all_todos', json.dumps(cache_data))
        logger.info("Updated all_todos cache with fresh data")
    except Exception as e:
        logger.error(f"Error updating all_todos cache: {e}")
        raise

@retry_on_error(max_retries=3)
def invalidate_all_todos_cache():
    """Invalidate the all_todos cache"""
    try:
        redis_client.delete('all_todos')
        logger.info("Invalidated all_todos cache")
    except Exception as e:
        logger.error(f"Error invalidating all_todos cache: {e}")
        raise

def process_notification(message):
    try:
        logger.info('Processing notification: %s', message)
        data = json.loads(message['Body'])
        logger.info('Parsed message body: %s', data)

        todo_id = data.get('todoId') or data.get('todo_id')
        action = data.get('type') or data.get('action')

        # Extract todo data from the message, excluding metadata fields
        todo_data = {
            'title': data.get('title'),
            'description': data.get('description'),
            'status': data.get('status', 'pending'),
            'priority': data.get('priority', 'medium'),
            'due_date': data.get('due_date')
        }
        logger.info('Extracted todo_data: %s', todo_data)

        logger.info('Notification details - ID: %s, Action: %s, Data: %s',
                   todo_id, action, todo_data)

        db = get_db_session()
        try:
            if action == 'todo_created':
                logger.info('Creating todo with ID: %s', todo_id)
                # Check if todo already exists
                existing_todo = db.query(Todo).filter(Todo.id == int(todo_id)).first()
                if existing_todo:
                    logger.info('Todo with ID %s already exists, skipping creation', todo_id)
                    return True  # Return True to indicate successful processing

                # Ensure required fields are present
                if not todo_data.get('title'):
                    logger.error('Title is required for todo creation. Available fields: %s', list(todo_data.keys()))
                    return False

                # Log the todo data before creation
                logger.info('Creating todo with data: %s', todo_data)

                todo = Todo(**todo_data)
                db.add(todo)
                db.commit()
                db.refresh(todo)
                update_all_todos_cache(db)  # Rebuild all todos cache
                logger.info('Successfully created todo: %s', todo_id)
                return True  # Return True to indicate successful processing

            elif action == 'todo_updated':
                logger.info('Updating todo with ID: %s', todo_id)
                todo = db.query(Todo).filter(Todo.id == int(todo_id)).first()
                if todo:
                    for key, value in todo_data.items():
                        setattr(todo, key, value)
                    db.commit()
                    db.refresh(todo)
                    update_all_todos_cache(db)  # Rebuild all todos cache
                    logger.info('Successfully updated todo: %s', todo_id)
                    return True  # Return True to indicate successful processing

            elif action == 'todo_deleted':
                logger.info('Deleting todo with ID: %s', todo_id)
                todo = db.query(Todo).filter(Todo.id == int(todo_id)).first()
                if todo:
                    db.delete(todo)
                    db.commit()
                update_all_todos_cache(db)
                logger.info('Successfully deleted todo: %s', todo_id)
                return True  # Return True to indicate successful processing

            return False  # Return False if no action was taken

        finally:
            db.close()

    except Exception as e:
        logger.error('Error processing notification: %s - Error: %s',
                    message, str(e), exc_info=True)
        raise

def main():
    logger.info("Starting worker...")

    # Initialize database
    init_db()

    while True:
        try:
            # Receive messages from the queue with increased visibility timeout
            response = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
                VisibilityTimeout=60  # Increased from 30 to 60 seconds
            )
            logger.info("SQS response: %s", response)

            if 'Messages' in response:
                for message in response['Messages']:
                    try:
                        # Process the message and check if it was successful
                        if process_notification(message):
                            # Only delete the message if processing was successful
                            sqs.delete_message(
                                QueueUrl=QUEUE_URL,
                                ReceiptHandle=message['ReceiptHandle']
                            )
                            logger.info("Successfully deleted message from queue")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        # Don't delete the message if processing failed
                        # It will be retried later
            else:
                logger.info("No messages in queue, waiting...")

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(5)  # Wait before retrying

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
