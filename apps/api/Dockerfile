FROM python:3.13-slim
WORKDIR /workspace/apps/api
COPY apps/api/requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY apps/api/ ./
RUN pip install --no-cache-dir --no-deps .
COPY data /workspace/data
COPY knowledge /workspace/knowledge
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
