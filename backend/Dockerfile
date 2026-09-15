# Deliberately does NOT install PaddleOCR — that pulls paddlepaddle plus model
# weights and turns a ~200 MB image into a multi-gigabyte one. When Phase 2
# self-hosts PP-StructureV3, give it its own image and service so the API stays
# small and deploys fast.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
