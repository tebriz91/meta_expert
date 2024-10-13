FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install minimal required build tools and dependencies for Playwright
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its dependencies
RUN playwright install-deps
RUN playwright install chromium firefox webkit

# Copy the rest of the application
COPY . .

# Copy the .env file to the Docker image
COPY .env .env

# Expose the port Chainlit runs on
EXPOSE 8105

# Command to run the application
CMD ["chainlit", "run", "main.py", "--port", "8105"]
