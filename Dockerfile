# Use the official Python 3.12.2 image as a base
FROM python:3.12.2-slim

# Set environment variables to ensure the Python output is not buffered
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt /app/requirements.txt

# Install system dependencies required for your libraries
RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev \
    tesseract-ocr \
    libtesseract-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install the SpaCy language model
RUN python -m spacy download en_core_web_sm

# Copy the application code into the container
COPY . /app

# Expose the default Flask port
EXPOSE 5000

# Define the command to run your application
# Start the app with Gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
