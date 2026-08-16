FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md requirements.txt main.py ./
COPY src ./src
RUN pip install --no-cache-dir . && pip install --no-cache-dir -r requirements.txt
EXPOSE 8088
ENV ALLY_AGENT=lexie
RUN PYTHONDONTWRITEBYTECODE= python -m compileall -q src main.py
CMD ["python", "main.py"]
