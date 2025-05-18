CREATE TABLE IF NOT EXISTS todos (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS todo_notifications (
    id SERIAL PRIMARY KEY,
    todo_id INTEGER NOT NULL,
    todo_title VARCHAR(100),
    todo_description TEXT,
    todo_status VARCHAR(20),
    todo_priority VARCHAR(20),
    todo_due_date TIMESTAMP WITH TIME ZONE,
    notification_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
