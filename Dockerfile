FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Газетир OSM з російськими назвами (не критично, якщо Overpass недоступний)
RUN python scripts/build_gazetteer.py || true
ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --ws-ping-interval 20
