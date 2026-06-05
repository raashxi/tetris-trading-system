FROM python:3.11-slim

# Install only essential system dependencies
RUN apt-get update && apt-get install -y curl git tzdata && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip

RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p logs models data

# Set timezone to IST
RUN ln -sf /usr/share/zoneinfo/Asia/Kolkata /etc/localtime && echo "Asia/Kolkata" > /etc/timezone


RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app

USER botuser


HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD python -c "import sys; sys.exit(0)"

RUN mkdir -p /home/botuser/.trading_bot && chown -R botuser:botuser /home/botuser/.trading_bot

CMD ["python", "src/main.py"]