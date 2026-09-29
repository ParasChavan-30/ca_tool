FROM php:8.2-apache

# Install PDO MySQL extension
RUN docker-php-ext-install pdo pdo_mysql

# Enable Apache rewrite module
RUN a2enmod rewrite

# Copy all project files into Apache web root
COPY . /var/www/html/

# Expose port 80 (Railway will map $PORT automatically)
EXPOSE 80
