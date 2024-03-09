# Set the base image to Python 3.8 Slim version
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the requirements file and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the enqueue directory
COPY enqueue/ ./enqueue

# Set the Python environment to recognize the 'enqueue' directory as a package
ENV PYTHONPATH /usr/src/app

# Run the enqueue server
CMD ["python", "-m", "enqueue.enqueue"]
