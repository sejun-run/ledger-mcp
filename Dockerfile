FROM python:3.12-slim
WORKDIR /app
COPY ledger_mcp.py pyproject.toml README.md .
RUN pip install --no-cache-dir .
ENV LEDGER_PATH=/data/ledger.json PORT=8000
VOLUME /data
EXPOSE 8000
CMD ["ledger-mcp", "--http"]
