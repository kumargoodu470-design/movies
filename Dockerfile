FROM python:3.12-slim

WORKDIR /app

COPY advanced_movie_bot/requirements.txt /app/requirements.txt
COPY advanced_movie_bot /app/advanced_movie_bot

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

WORKDIR /app/advanced_movie_bot

CMD ["python", "bot.py"]
