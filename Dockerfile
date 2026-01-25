FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Using -m to ensure imports work correctly
CMD ["python", "-m", "app.main"]
