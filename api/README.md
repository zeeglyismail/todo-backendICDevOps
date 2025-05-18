# API Service (FastAPI)

This service provides RESTful CRUD endpoints for managing todos.

- Integrates with Redis for caching
- Publishes write operations to SQS
- Handles authentication and authorization

## Testing

To run API service tests:

```
pytest
```
Or using Docker:
```
docker build -t todo-api-test .
docker run --rm todo-api-test pytest
```
- Tests are located in `tests/test_health.py` and cover the `/health` endpoint for status and response.
