import os
import sys
import boto3
import psycopg2
import redis
from psycopg2 import sql
from dotenv import load_dotenv
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL') or (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)

# Redis configuration
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT'))

# SQS configuration
SQS_REGION = os.getenv('SQS_REGION', 'ap-southeast-1')

# Queue configuration
QUEUE_NAME = os.getenv('SQS_QUEUE_NAME')
QUEUE_URL = os.getenv('SQS_QUEUE_URL')
DLQ_URL = os.getenv('SQS_DLQ_URL')

# SQS setup
def ensure_sqs_queue():
    # Configure SQS client
    sqs_config = {
        'region_name': SQS_REGION,
    }

    # Only add endpoint URL and credentials for local development
    if 'elasticmq' in QUEUE_URL:
        sqs_config.update({
            'endpoint_url': QUEUE_URL,
            'aws_access_key_id': '1234',
            'aws_secret_access_key': '1234'
        })

    sqs = boto3.client('sqs', **sqs_config)

    try:
        # Verify queue access
        sqs.get_queue_attributes(
            QueueUrl=QUEUE_URL,
            AttributeNames=['QueueArn']
        )
        logger.info("SQS queue access verified.")
    except Exception as e:
        logger.error(f"Error accessing SQS queue: {e}")
        sys.exit(1)

# DB setup
def ensure_db_table():
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            port=int(os.getenv('POSTGRES_PORT')),
            database=os.getenv('POSTGRES_DB'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD')
        )
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS todos (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                due_date TIMESTAMP,
                priority VARCHAR(50) DEFAULT 'medium',
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Database table 'todos' ensured.")
    except Exception as e:
        logger.error(f"Error ensuring DB table: {e}")
        sys.exit(1)

# Redis setup
def ensure_redis():
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT
        )
        r.ping()
        logger.info("Redis connection ensured.")
    except Exception as e:
        logger.error(f"Error ensuring Redis: {e}")
        sys.exit(1)

def initialize_services():
    ensure_sqs_queue()
    ensure_db_table()
    ensure_redis()
