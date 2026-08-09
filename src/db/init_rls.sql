-- ============================================================================
-- Enterprise Multi-Tenant RLS & Security Isolation Setup
-- ============================================================================

-- 1. Enable Vector Extension for Schema RAG
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS vector;
    EXCEPTION WHEN OTHERS THEN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector') THEN
            CREATE DOMAIN vector AS text;
        END IF;
    END;
END
$$;

-- 2. Create Low-Privilege Read-Only Runner Role
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_read_only_runner') THEN
        CREATE ROLE agent_read_only_runner WITH LOGIN PASSWORD 'read_only_secure_pass';
    END IF;
END
$$;

-- Enforce strict statement and memory boundaries on execution role
ALTER ROLE agent_read_only_runner SET statement_timeout = '10s';
ALTER ROLE agent_read_only_runner SET work_mem = '64MB';
ALTER ROLE agent_read_only_runner SET default_transaction_read_only = 'on';

-- 3. Core Multi-Tenant Catalogs & Tables
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schema_catalog (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    table_name VARCHAR(128) NOT NULL,
    column_name VARCHAR(128) NOT NULL,
    data_type VARCHAR(64) NOT NULL,
    is_nullable BOOLEAN DEFAULT TRUE,
    is_primary_key BOOLEAN DEFAULT FALSE,
    is_foreign_key BOOLEAN DEFAULT FALSE,
    foreign_table VARCHAR(128),
    foreign_column VARCHAR(128),
    is_pii BOOLEAN DEFAULT FALSE,
    description TEXT,
    embedding vector,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    ssn VARCHAR(32),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Enable Row Level Security (RLS)
ALTER TABLE schema_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;

-- 5. Define Tenant Isolation Policies using session context
DROP POLICY IF EXISTS tenant_isolation_schema_catalog ON schema_catalog;
CREATE POLICY tenant_isolation_schema_catalog ON schema_catalog
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

DROP POLICY IF EXISTS tenant_isolation_orders ON orders;
CREATE POLICY tenant_isolation_orders ON orders
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

DROP POLICY IF EXISTS tenant_isolation_customers ON customers;
CREATE POLICY tenant_isolation_customers ON customers
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- 6. Grant Read-Only Permissions
GRANT CONNECT ON DATABASE enterprise_db TO agent_read_only_runner;
GRANT USAGE ON SCHEMA public TO agent_read_only_runner;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_read_only_runner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agent_read_only_runner;
