FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly copy templates and main file
COPY templates/ /app/templates/
COPY main.py /app/

# Cloud Run/Render expects port 8080 or $PORT
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
