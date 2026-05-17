FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir flask gunicorn
EXPOSE 7860
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860"]
