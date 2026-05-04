FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml .
COPY app ./app

RUN pip install --no-cache-dir .

COPY . .

ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
