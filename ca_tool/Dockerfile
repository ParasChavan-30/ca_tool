FROM php:8.2-cli

# Install PDO MySQL extension
RUN docker-php-ext-install pdo pdo_mysql

# Copy project files
WORKDIR /var/www/html
COPY . .

# Expose port 8080
EXPOSE 8080

# Run PHP built-in web server listening on 0.0.0.0:8080
CMD ["php", "-S", "0.0.0.0:8080"]
