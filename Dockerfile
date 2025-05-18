FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY elasticmq.conf /elasticmq.conf

EXPOSE 3001

CMD ["gunicorn", "--bind", "0.0.0.0:3001", "app:app"]
