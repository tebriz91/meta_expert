FROM python:3.12-slim

ENV PATH=/root/.cargo/bin:$PATH

# Install uv and other dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    gcc \
    g++ \
    python3-dev \
    wget \
    && curl -LsSf https://astral.sh/uv/install.sh -o /tmp/install_uv.sh \
    && chmod +x /tmp/install_uv.sh \
    && sh /tmp/install_uv.sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create and activate virtual environment
RUN uv venv /venv
ENV PATH=/venv/bin:$PATH

# Copy application-specific dependencies and install them
COPY requirements.txt /app
RUN uv pip install --no-cache-dir -r requirements.txt

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