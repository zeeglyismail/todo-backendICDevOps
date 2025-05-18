from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Todo(Base):
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(Text)
    status = Column(String(20), default='pending')
    priority = Column(String(20), default='medium')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)

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
