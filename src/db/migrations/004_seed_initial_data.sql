-- Migration 004: Seed Initial Multi-Tenant Test Data

-- Insert Sample Tenant
INSERT INTO tenants (id, name)
VALUES 
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Acme Corporation'),
    ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'Globex Industries')
ON CONFLICT DO NOTHING;

-- Insert Sample Customers for Acme Corp
INSERT INTO customers (id, tenant_id, full_name, email, ssn, created_at)
VALUES
    ('c0010000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Alice Smith', 'alice@acme.com', '999-11-0001', NOW() - INTERVAL '6 months'),
    ('c0020000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Bob Jones', 'bob@acme.com', '999-11-0002', NOW() - INTERVAL '5 months'),
    ('c0030000-0000-0000-0000-000000000003', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Carol White', 'carol@acme.com', '999-11-0003', NOW() - INTERVAL '4 months')
ON CONFLICT DO NOTHING;

-- Insert Sample Products
INSERT INTO products (id, tenant_id, sku, name, category, price)
VALUES
    ('e0010000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'PROD-001', 'Enterprise Analytics Suite', 'Software', 1250.00),
    ('e0020000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'PROD-002', 'Cloud Storage Pro 1TB', 'Cloud Services', 450.00)
ON CONFLICT DO NOTHING;

-- Insert Sample Orders
INSERT INTO orders (id, tenant_id, customer_id, total_amount, status, created_at)
VALUES
    ('f0010000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0010000-0000-0000-0000-000000000001', 1250.00, 'completed', NOW() - INTERVAL '3 months'),
    ('f0020000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0010000-0000-0000-0000-000000000001', 450.00, 'completed', NOW() - INTERVAL '2 months'),
    ('f0030000-0000-0000-0000-000000000003', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0020000-0000-0000-0000-000000000002', 3100.00, 'completed', NOW() - INTERVAL '1 month')
ON CONFLICT DO NOTHING;

-- Insert Schema Catalog Metadata for RAG
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

-- Insert Sample Order Events
INSERT INTO order_events (id, tenant_id, order_id, previous_status, new_status, created_at)
VALUES
    ('90010000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0010000-0000-0000-0000-000000000001', 'pending', 'processing', NOW() - INTERVAL '3 months' - INTERVAL '2 days'),
    ('90010000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0010000-0000-0000-0000-000000000001', 'processing', 'shipped', NOW() - INTERVAL '3 months' - INTERVAL '1 days'),
    ('90010000-0000-0000-0000-000000000003', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0010000-0000-0000-0000-000000000001', 'shipped', 'delivered', NOW() - INTERVAL '3 months'),
    
    ('90020000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0020000-0000-0000-0000-000000000002', 'pending', 'processing', NOW() - INTERVAL '2 months' - INTERVAL '3 days'),
    ('90020000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0020000-0000-0000-0000-000000000002', 'processing', 'cancelled', NOW() - INTERVAL '2 months'),
    
    ('90030000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0030000-0000-0000-0000-000000000003', 'pending', 'processing', NOW() - INTERVAL '1 month')
ON CONFLICT DO NOTHING;

-- Insert Sample Loan Applications
INSERT INTO loan_applications (id, tenant_id, customer_id, credit_score, income, debt, decision_status, created_at)
VALUES
    ('80010000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0010000-0000-0000-0000-000000000001', 750, 85000.00, 15000.00, 'Approved', NOW()),
    ('80020000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0020000-0000-0000-0000-000000000002', 620, 45000.00, 25000.00, 'Rejected', NOW()),
    ('80030000-0000-0000-0000-000000000003', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0030000-0000-0000-0000-000000000003', 680, 55000.00, 10000.00, 'Manual Review', NOW()),
    ('80040000-0000-0000-0000-000000000004', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'c0010000-0000-0000-0000-000000000001', 810, 120000.00, 5000.00, 'Approved', NOW())
ON CONFLICT DO NOTHING;
