FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
	--index-url https://download.pytorch.org/whl/cpu \
	--extra-index-url https://pypi.org/simple \
	"torch==2.7.1+cpu"
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY knowledge ./knowledge

CMD ["sh", "-c", "exec uvicorn app.webhook:app --host 0.0.0.0 --port ${PORT:-8080}"]