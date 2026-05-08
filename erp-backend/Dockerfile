FROM python:3.10-slim-bookworm

WORKDIR /app

# Install Python dependencies (uses prebuilt wheels for most packages)
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.cloud.tencent.com/pypi/simple -r requirements.txt

# Copy source code
COPY . .

EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
