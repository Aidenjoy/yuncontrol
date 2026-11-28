FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY yunwork_cloud ./yunwork_cloud
RUN pip install --no-cache-dir .

EXPOSE 8090
CMD ["uvicorn", "yunwork_cloud.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8090"]
