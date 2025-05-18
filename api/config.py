import os
import sys
import boto3
import psycopg2
import redis
from psycopg2 import sql
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL') or (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)

# Redis configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

# SQS configuration
SQS_ENDPOINT = os.getenv('SQS_ENDPOINT', 'http://elasticmq:9324')
SQS_REGION = os.getenv('SQS_REGION', 'elasticmq')
SQS_ACCESS_KEY = os.getenv('SQS_ACCESS_KEY', 'x')
SQS_SECRET_KEY = os.getenv('SQS_SECRET_KEY', 'x')

# Queue names and URLs
QUEUE_NAME = 'todo-notifications'
DLQ_NAME = f'{QUEUE_NAME}-dlq'
QUEUE_URL = f"{SQS_ENDPOINT}/queue/{QUEUE_NAME}"
DLQ_URL = f"{SQS_ENDPOINT}/queue/{DLQ_NAME}"

# SQS setup
def ensure_sqs_queue():
    # Configure SQS client
    sqs_config = {
        'region_name': SQS_REGION,
        'endpoint_url': SQS_ENDPOINT,
    }

    # Only add endpoint URL and credentials for local development
    if 'elasticmq' in SQS_ENDPOINT:
        sqs_config.update({
            'aws_access_key_id': SQS_ACCESS_KEY,
            'aws_secret_access_key': SQS_SECRET_KEY
        })

    sqs = boto3.client('sqs', **sqs_config)

    try:
        # Create DLQ first
        sqs.create_queue(
            QueueName=DLQ_NAME,
            Attributes={
                'VisibilityTimeout': '10',
                'DelaySeconds': '0',
                'ReceiveMessageWaitTimeSeconds': '0'
            }
        )
        # Create main queue
        sqs.create_queue(
            QueueName=QUEUE_NAME,
            Attributes={
                'VisibilityTimeout': '10',
                'DelaySeconds': '0',
                'ReceiveMessageWaitTimeSeconds': '0',
                'RedrivePolicy': '{"deadLetterTargetArn":"arn:aws:sqs:elasticmq:000000000000:' + DLQ_NAME + '","maxReceiveCount":"3"}'
            }
        )
        print(f"SQS queues '{QUEUE_NAME}' and '{DLQ_NAME}' ensured.")
    except Exception as e:
        print(f"Error ensuring SQS queues: {e}")
        sys.exit(1)

# DB setup
def ensure_db_table():
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
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
        print("Database table 'todos' ensured.")
    except Exception as e:
        print(f"Error ensuring DB table: {e}")
        sys.exit(1)

# Redis setup
def ensure_redis():
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT
        )
        r.ping()
        print("Redis connection ensured.")
    except Exception as e:
        print(f"Error ensuring Redis: {e}")
        sys.exit(1)

def initialize_services():
    ensure_sqs_queue()
    ensure_db_table()
    ensure_redis()
