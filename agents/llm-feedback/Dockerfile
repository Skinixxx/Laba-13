FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import sys; sys.exit(0)"

CMD ["python", "main.py"]
