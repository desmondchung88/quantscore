-- =====================================================================
--  Create the application database user.
--
--  WHY THIS EXISTS
--  MariaDB on Windows often configures root@localhost to authenticate
--  through Windows SSPI (the auth_gssapi_client plugin) rather than with
--  a password. The MariaDB command-line client speaks that protocol; the
--  Python driver (PyMySQL) does not, and fails with:
--
--      (2059, "Authentication plugin 'auth_gssapi_client' not configured")
--
--  No password in .env can fix that, because root is not using password
--  authentication at all. The answer is a dedicated application account
--  that uses mysql_native_password -- which is better practice anyway:
--  the app should not be running as root.
--
--  HOW TO RUN IT
--  Open HeidiSQL (installed with MariaDB) or "MariaDB Command Prompt"
--  from the Start menu, connect as root, and run this file. From a shell:
--
--      mysql -u root -p < backend/sql/00_create_user.sql
--
--  Then set these two lines in .env:
--
--      MYSQL_USER=quantscore
--      MYSQL_PASSWORD=quantscore
--
--  Change the password below first if this is not a throwaway machine.
-- =====================================================================

CREATE USER IF NOT EXISTS 'quantscore'@'localhost'
    IDENTIFIED BY 'quantscore';
CREATE USER IF NOT EXISTS 'quantscore'@'127.0.0.1'
    IDENTIFIED BY 'quantscore';

-- Force password authentication. On MariaDB, IDENTIFIED BY already picks
-- mysql_native_password, but being explicit means this also works if the
-- server default is something the Python driver cannot negotiate.
ALTER USER 'quantscore'@'localhost'
    IDENTIFIED VIA mysql_native_password USING PASSWORD('quantscore');
ALTER USER 'quantscore'@'127.0.0.1'
    IDENTIFIED VIA mysql_native_password USING PASSWORD('quantscore');

-- Privileges are scoped to this one database. Granting on a database that
-- does not exist yet is allowed and is what lets the ETL run its
-- CREATE DATABASE / DROP DATABASE statements.
GRANT ALL PRIVILEGES ON quantscore.* TO 'quantscore'@'localhost';
GRANT ALL PRIVILEGES ON quantscore.* TO 'quantscore'@'127.0.0.1';

FLUSH PRIVILEGES;

SELECT 'quantscore user created -- now set MYSQL_USER and MYSQL_PASSWORD in .env'
       AS next_step;
