FROM php:8.2-apache

# Install PDO MySQL extension
RUN docker-php-ext-install pdo pdo_mysql

# Enable Apache rewrite module
RUN a2enmod rewrite

# Copy all project files into Apache web root
COPY . /var/www/html/

# Rebind Apache port specifically to Railway $PORT
CMD sh -c "PORT=\${PORT:-80} && sed -i \"s/Listen 80/Listen \$PORT/g\" /etc/apache2/ports.conf && sed -i \"s/<VirtualHost \*:80>/<VirtualHost \*:\$PORT>/g\" /etc/apache2/sites-available/000-default.conf && apache2-foreground"


