# Base image
FROM python:3.9

# Set working directory
WORKDIR /app

# Copy application files specific to dataprocess
COPY . /app

RUN pip install scikit-learn==1.3.2 torch transformers>=4.0.0

# Install dependencies from the local requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose FastAPI port
EXPOSE 8001

# Run FastAPI server
CMD ["uvicorn", "dataprocess_server:app", "--host", "0.0.0.0", "--port", "8001"]
