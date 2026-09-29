FROM php:8.2-cli

# Install system dependencies, python3, pip, libxml2, libffi, build tools
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    libxml2-dev \
    libffi-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PDO MySQL extension
RUN docker-php-ext-install pdo pdo_mysql

# Set working directory
WORKDIR /var/www/html

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt || pip3 install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Ensure storage directories exist with write permissions
RUN mkdir -p storage/pdfs storage/logs storage/db && chmod -R 777 storage

# Expose port 8080
EXPOSE 8080

# Run PHP built-in web server listening on 0.0.0.0:8080
CMD ["php", "-S", "0.0.0.0:8080"]
