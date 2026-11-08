FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock.txt ./
COPY kitchen/ ./kitchen/
RUN pip install --no-cache-dir -c requirements.lock.txt .
COPY --from=web /web/dist ./frontend/dist
ENV KITCHEN_HOST=0.0.0.0 KITCHEN_PORT=8000 KITCHEN_DATA_DIR=/var/data KITCHEN_ENABLE_LIVE=0
EXPOSE 8000
CMD ["python", "-m", "kitchen"]
