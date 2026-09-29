-- CA Knowledge Bank Tool Database Schema
-- Compatible with MySQL / MariaDB (cPanel / phpMyAdmin)

SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `sources` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(255) NOT NULL,
  `domain` VARCHAR(255) NOT NULL UNIQUE,
  `url` VARCHAR(500) NOT NULL,
  `is_primary` TINYINT(1) DEFAULT 0,
  `status` VARCHAR(50) DEFAULT 'PENDING',
  `failure_count` INT DEFAULT 0,
  `last_checked` DATETIME NULL,
  `total_scraped_items` INT DEFAULT 0,
  `failover_priority` INT DEFAULT 99,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `knowledge_bank` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `source_id` INT NOT NULL,
  `source_url` VARCHAR(768) NOT NULL UNIQUE,
  `title` VARCHAR(500) NOT NULL,
  `authority_category` VARCHAR(255) NOT NULL,
  `notification_number` VARCHAR(255) NULL,
  `summary` TEXT NULL,
  `published_date` DATE NULL,
  `full_html_content` LONGTEXT,
  `content_hash` VARCHAR(64) NULL,
  `collected_date` DATETIME NOT NULL,
  `last_updated_at` DATETIME NULL,
  `wp_post_id` INT NULL,
  `wp_synced_at` DATETIME NULL,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`source_id`) REFERENCES `sources`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `knowledge_bank_sources` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `knowledge_bank_id` INT NOT NULL,
  `source_id` INT NOT NULL,
  `source_url` VARCHAR(768) NOT NULL UNIQUE,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`knowledge_bank_id`) REFERENCES `knowledge_bank`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`source_id`) REFERENCES `sources`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `sub_pages` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `knowledge_bank_id` INT NOT NULL,
  `sub_page_url` VARCHAR(768) NOT NULL,
  `sub_page_title` VARCHAR(500),
  `sub_page_html` LONGTEXT,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`knowledge_bank_id`) REFERENCES `knowledge_bank`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attachments` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `knowledge_bank_id` INT NOT NULL,
  `file_name` VARCHAR(255) NOT NULL,
  `file_url` VARCHAR(768) NOT NULL,
  `local_storage_path` VARCHAR(500) NOT NULL,
  `file_size_bytes` BIGINT DEFAULT 0,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`knowledge_bank_id`) REFERENCES `knowledge_bank`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `execution_logs` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `source_id` INT NULL,
  `run_timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `status` VARCHAR(50) NOT NULL,
  `items_scraped` INT DEFAULT 0,
  `items_added` INT DEFAULT 0,
  `items_updated` INT DEFAULT 0,
  `items_unchanged` INT DEFAULT 0,
  `wp_posts_updated` INT DEFAULT 0,
  `log_details` TEXT,
  `error_message` TEXT,
  FOREIGN KEY (`source_id`) REFERENCES `sources`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `cron_settings` (
  `setting_key` VARCHAR(100) PRIMARY KEY,
  `setting_value` TEXT NULL,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `cron_settings` (`setting_key`, `setting_value`) VALUES
('cron_enabled', '1'),
('cron_interval_hours', '24'),
('last_cron_run', NULL),
('cron_secret_token', 'ca_cron_secret_key_123')
ON DUPLICATE KEY UPDATE `setting_key` = VALUES(`setting_key`);


-- Initial Source Seeding
INSERT INTO `sources` (`name`, `domain`, `url`, `is_primary`, `failover_priority`, `status`)
VALUES
('SCA & Associates', 'scaca.in', 'https://scaca.in/', 1, 0, 'ACTIVE'),
('Pankaj Lunker & Associates', 'pankajlunkerassociates.com', 'https://pankajlunkerassociates.com/', 0, 1, 'PENDING'),
('Nexus Advisors', 'nexusadvisors.co.in', 'https://nexusadvisors.co.in/', 0, 2, 'PENDING'),
('Shah Sol', 'shahsol.com', 'https://shahsol.com/', 0, 3, 'PENDING'),
('Sujata Bharti', 'sujatabharti.com', 'https://sujatabharti.com/', 0, 4, 'PENDING'),
('Step Ladder', 'stepladder.in', 'https://stepladder.in/', 0, 5, 'PENDING'),
('Sunil Kapoor & Associates', 'sunilkapoorandassociates.com', 'https://sunilkapoorandassociates.com/', 0, 6, 'PENDING'),
('Virendra Associates', 'virendraassociates.com', 'https://virendraassociates.com/', 0, 7, 'PENDING'),
('Skymap Alliance', 'skymapalliance.in', 'https://skymapalliance.in/', 0, 8, 'PENDING'),
('PPD & Company', 'ppdandcompany.com', 'https://ppdandcompany.com/', 0, 9, 'PENDING'),
('SRG Finserv', 'srgfinserv.com', 'https://srgfinserv.com/', 0, 10, 'PENDING')
ON DUPLICATE KEY UPDATE `is_primary` = VALUES(`is_primary`);

SET FOREIGN_KEY_CHECKS = 1;
