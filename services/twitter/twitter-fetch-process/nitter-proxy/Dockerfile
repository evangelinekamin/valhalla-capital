FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN useradd -m -u 1000 nitterproxy || true && chown -R 1000:1000 /app
USER 1000

EXPOSE 8090

CMD ["python", "main.py"]
