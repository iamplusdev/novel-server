"""Docker 镜像：零多余系统依赖，基于官方 Python slim。"""
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    NOVELS_DIR=/app/novels \
    DATABASE_PATH=/app/data/novels.db \
    COVERS_DIR=/app/covers

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 暴露卷挂载点说明：/app/novels /app/data /app/covers
EXPOSE 8000

CMD ["python", "run.py"]
