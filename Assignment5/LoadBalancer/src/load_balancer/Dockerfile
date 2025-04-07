FROM python:3.10-alpine AS builder
COPY requirements.txt /
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /wheels --timeout 100 -r /requirements.txt

FROM python:3.10-alpine
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY --from=builder /requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links /wheels --requirement requirements.txt && \
    rm -rf /wheels /requirements.txt
COPY . .
CMD ["python", "loadBalancer.py"]
