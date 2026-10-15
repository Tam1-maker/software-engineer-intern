FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN python -m pip install \
    --no-cache-dir \
    --requirement /app/requirements.txt

COPY q1_api /app/q1_api

WORKDIR /app/q1_api

RUN mkdir -p /data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
