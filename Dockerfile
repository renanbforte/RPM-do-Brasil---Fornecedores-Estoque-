# Imagem do backend de estoque (API de consulta + pipeline de ingestão).
FROM python:3.12-slim

WORKDIR /app

# Dependências primeiro (melhor cache de build)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY . .

# O banco fica num VOLUME PERSISTENTE montado em /data (ver EasyPanel).
# A ingestão ESCREVE em DB_PATH e a API LÊ de DATABASE_PATH — os dois
# apontam para o mesmo arquivo no volume.
ENV DB_PATH=/data/estoque.db
ENV DATABASE_PATH=/data/estoque.db
# (defina também API_TOKEN, e — se for rodar a ingestão — OPENAI_API_KEY,
#  FONTE, GDRIVE_FOLDER_ID e GOOGLE_APPLICATION_CREDENTIALS como env vars)

EXPOSE 8000

# Sobe a API. Health check do EasyPanel: GET /health
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
