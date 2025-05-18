# Worker Service

Consumes messages from SQS, processes write operations, updates MySQL and Redis cache.

- Ensures data consistency
- Decouples write operations from API

## Testing

To run worker service tests:

```
pytest
```
Or using Docker:
```
docker build -t todo-worker-test .
docker run --rm todo-worker-test pytest
```
- Tests are located in `tests/test_health.py` and cover the `/health` endpoint for status and response.
