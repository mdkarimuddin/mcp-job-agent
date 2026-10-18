FROM python:3.11-slim
WORKDIR /app
RUN useradd -m app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY data/sample_applications.csv ./data/sample_applications.csv
USER app
ENV JOBAGENT_DB=/home/app/jobs.db
CMD ["python", "-m", "jobagent.server"]
