-- Runs once, the first time the `pgdata` volume is created, because the
-- postgres image only executes /docker-entrypoint-initdb.d on a fresh data
-- directory. On a volume that already exists, create it by hand instead:
--
--   docker compose exec db createdb -U scribble scribble2notes_test
--
-- The persistence tests get their own database because they TRUNCATE between
-- cases. Pointed at your development database they would erase your saved
-- pages every time you ran the suite.
CREATE DATABASE scribble2notes_test OWNER scribble;
