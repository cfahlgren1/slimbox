# Set the base image to Python 3.8 Slim version
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the requirements file and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the worker directory
COPY worker/ ./worker

# Copy the enqueue directory to access shared code like 'tasks.py'
COPY enqueue/ ./enqueue

# Set the Python environment to recognize the 'enqueue' directory as a package
ENV PYTHONPATH /usr/src/app

# Run the worker process
CMD ["python", "-m", "worker.worker"]
