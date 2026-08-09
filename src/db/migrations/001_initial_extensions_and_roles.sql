-- Migration 001: Initial Extensions and Execution Roles

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- Low-privilege read-only runner role for safe query execution
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_read_only_runner') THEN
        CREATE ROLE agent_read_only_runner WITH LOGIN PASSWORD 'read_only_secure_pass';
    END IF;
END
$$;

-- Enforce strict statement limits on the execution role
ALTER ROLE agent_read_only_runner SET statement_timeout = '10s';
ALTER ROLE agent_read_only_runner SET work_mem = '64MB';
ALTER ROLE agent_read_only_runner SET default_transaction_read_only = 'on';
