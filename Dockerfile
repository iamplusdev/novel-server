# Docker 镜像：零多余系统依赖，基于官方 Python slim。
# 用户数据（data/covers/novels）一律挂载 volume，不打进镜像。
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

# 只拷运行所需代码（.dockerignore 已排除 data/covers/novels/scripts）
COPY app ./app
COPY run.py import_novels.py reset_auth.py ./
COPY index.html admin.css admin.js favicon.ico legado_book_source.json ./

# 挂载点：/app/novels /app/data /app/covers
VOLUME ["/app/novels", "/app/data", "/app/covers"]
EXPOSE 8000

CMD ["python", "run.py"]
