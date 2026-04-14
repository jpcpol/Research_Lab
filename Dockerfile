FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

ENV DATABASE_URL=sqlite:///./data/research.db
ENV SECRET_KEY=change-me-in-production
ENV TOKEN_EXPIRE_HOURS=72

RUN mkdir -p /app/data

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
