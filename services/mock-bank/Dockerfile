FROM python:3.13-slim

WORKDIR /app
COPY requirements-bank.txt ./
RUN pip install --no-cache-dir -r requirements-bank.txt
COPY . .

ENV PYTHONPATH=/app
CMD ["uvicorn", "mock_bank.api:app", "--host", "0.0.0.0", "--port", "8001"]
