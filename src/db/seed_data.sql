-- ============================================================================
-- Enterprise Multi-Tenant Sample Seed Data
-- ============================================================================

-- 1. Insert Sample Tenant
INSERT INTO tenants (id, name)
VALUES 
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Acme Corporation'),
    ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'Globex Industries')
ON CONFLICT DO NOTHING;

-- 2. Insert Sample Customers for Acme Corp
INSERT INTO customers (id, tenant_id, full_name, email, ssn, created_at)
VALUES
    ('c0010000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Alice Smith', 'alice@acme.com', '999-11-0001', NOW() - INTERVAL '6 months'),
    ('c0020000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Bob Jones', 'bob@acme.com', '999-11-0002', NOW() - INTERVAL '5 months'),
    ('c0030000-0000-0000-0000-000000000003', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Carol White', 'carol@acme.com', '999-11-0003', NOW() - INTERVAL '4 months'),
    ('c0040000-0000-0000-0000-000000000004', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'David Miller', 'david@acme.com', '999-11-0004', NOW() - INTERVAL '3 months')
ON CONFLICT DO NOTHING;

-- 3. Insert Sample Orders for Acme Corp
INSERT INTO orders (id, tenant_id, customer_id, total_amount, status, created_at)
VALUES
    ('f0010000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0010000-0000-0000-0000-000000000001', 1250.50, 'completed', NOW() - INTERVAL '3 months'),
    ('f0020000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0010000-0000-0000-0000-000000000001', 850.00, 'completed', NOW() - INTERVAL '2 months'),
    ('f0030000-0000-0000-0000-000000000003', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0020000-0000-0000-0000-000000000002', 3100.00, 'completed', NOW() - INTERVAL '1 month'),
    ('f0040000-0000-0000-0000-000000000004', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0030000-0000-0000-0000-000000000003', 450.25, 'pending', NOW() - INTERVAL '5 days')
ON CONFLICT DO NOTHING;

-- 4. Insert Schema Catalog Entries for Schema RAG
INSERT INTO schema_catalog (tenant_id, table_name, column_name, data_type, is_primary_key, is_foreign_key, is_pii, description)
VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'customers', 'id', 'UUID', true, false, false, 'Unique customer primary key identifier'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'customers', 'full_name', 'VARCHAR(255)', false, false, false, 'Customer display name'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'customers', 'email', 'VARCHAR(255)', false, false, true, 'Customer contact email address (PII)'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'customers', 'ssn', 'VARCHAR(32)', false, false, true, 'Social security number (PII)'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'orders', 'id', 'UUID', true, false, false, 'Unique order primary key identifier'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'orders', 'customer_id', 'UUID', false, true, false, 'Foreign key pointing to customers table'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'orders', 'total_amount', 'NUMERIC(12,2)', false, false, false, 'Total monetary amount for order'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'orders', 'status', 'VARCHAR(50)', false, false, false, 'Order state: completed, pending, cancelled')
ON CONFLICT DO NOTHING;
