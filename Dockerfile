FROM python:3.12-slim

# System dependencies install karna zaroori hai
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 8080
CMD ["python", "bot.py"]
