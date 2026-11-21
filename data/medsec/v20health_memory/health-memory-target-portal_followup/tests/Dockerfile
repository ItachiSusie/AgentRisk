FROM python:3.12-slim
WORKDIR /workspace
COPY evaluator.py answer_key.json test.sh /tests/
RUN chmod +x /tests/test.sh
CMD ["sleep", "infinity"]
