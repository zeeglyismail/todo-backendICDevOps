import os
import sys
import boto3
import psycopg2
import redis
from psycopg2 import sql
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection
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

# SQLAlchemy setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class Todo(Base):
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    description = Column(Text)
    status = Column(String(20), default='pending')
    priority = Column(String(20), default='medium')
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'priority': self.priority,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class TodoNotification(Base):
    __tablename__ = 'todo_notifications'

    id = Column(Integer, primary_key=True)
    todo_id = Column(Integer)
    todo_title = Column(String(100))
    todo_description = Column(Text)
    todo_status = Column(String(20))
    todo_priority = Column(String(20))
    todo_due_date = Column(DateTime, nullable=True)
    notification_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Dependency injection-style DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize all tables
def init_db():
    Base.metadata.create_all(bind=engine)

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
