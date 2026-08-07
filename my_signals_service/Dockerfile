FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY my_signals_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code + My Signals package (device_care)
COPY my_signals_service/app.py /app/app.py
COPY my_signals_service/start.sh /app/start.sh
COPY device_care /app/device_care

RUN chmod +x /app/start.sh \
    && mkdir -p /app/device_care/data /app/device_care/uploads

ENV PORT=8000
ENV MY_SIGNALS_PREFIX=
ENV MY_SIGNALS_VERSION=4.1.4
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["./start.sh"]
