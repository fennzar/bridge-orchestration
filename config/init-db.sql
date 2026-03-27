-- Initialize databases for Zephyr Bridge Stack
-- This runs automatically when the postgres container starts fresh

-- Bridge database
CREATE DATABASE zephyrbridge_dev;
GRANT ALL PRIVILEGES ON DATABASE zephyrbridge_dev TO zephyr;

-- Engine database
CREATE DATABASE zephyr_bridge_arb;
GRANT ALL PRIVILEGES ON DATABASE zephyr_bridge_arb TO zephyr;

-- Scanner database
CREATE USER zephyrdscanner WITH PASSWORD 'zephyrdscanner';
CREATE DATABASE zephyrdscanner;
GRANT ALL PRIVILEGES ON DATABASE zephyrdscanner TO zephyrdscanner;

-- Connect to each database and grant schema permissions
\c zephyrbridge_dev
GRANT ALL ON SCHEMA public TO zephyr;

\c zephyr_bridge_arb
GRANT ALL ON SCHEMA public TO zephyr;

\c zephyrdscanner
GRANT ALL ON SCHEMA public TO zephyrdscanner;
