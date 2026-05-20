FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY user-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY shared /app/shared
COPY user-service/app /app/app
ENV PYTHONPATH=/app
EXPOSE 8506
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8506"]
