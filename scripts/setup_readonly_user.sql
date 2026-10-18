-- MovieList read-only database account for the Kodi video library.
--
-- Run MANUALLY as a MariaDB administrator on the Kodi host, e.g.:
--   sudo mysql < scripts/setup_readonly_user.sql
-- or adapt and execute through your preferred MySQL client.
--
-- Replace CHANGE_ME_STRONG_PASSWORD and the host pattern before running.
--
-- 'VIDEOAI_HOST' should be the hostname or IP that MovieList connects
-- from (the videoai machine).  Using a specific host is safer than '%'.
-- For a one-box setup where Kodi and MovieList share a host, use 'localhost'.

CREATE USER IF NOT EXISTS 'movielist'@'VIDEOAI_HOST'
  IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';

GRANT SELECT ON MyVideos131.* TO 'movielist'@'VIDEOAI_HOST';

FLUSH PRIVILEGES;

-- If Kodi is later upgraded to a new database (e.g. MyVideos132), grant
-- access to the NEW database explicitly and set KODI_DB_NAME accordingly:
--   GRANT SELECT ON MyVideos132.* TO 'movielist'@'VIDEOAI_HOST';
