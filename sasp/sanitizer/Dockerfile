FROM python:3.11-slim
WORKDIR /app
COPY ../../pyproject.toml .
COPY ../../sasp/ ./sasp/
RUN pip install --no-cache-dir .
CMD ["python", "-m", "sasp.sanitizer.cli"]
