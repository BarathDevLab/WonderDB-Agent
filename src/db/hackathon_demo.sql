-- ============================================================================
-- Hackathon Presentation Demo Database Setup (Expanded Schema)
-- 6 Months of Spread Data (20 Representative Records)
-- ============================================================================

-- Recommended Database Name for the Pitch
-- CREATE DATABASE ecom_production_db;
-- \c ecom_production_db;

-- 0. System Tables for AI Agent (Schema RAG)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    table_name VARCHAR(255) NOT NULL,
    column_name VARCHAR(255) NOT NULL,
    data_type VARCHAR(255) NOT NULL,
    is_primary_key BOOLEAN DEFAULT FALSE,
    is_foreign_key BOOLEAN DEFAULT FALSE,
    foreign_table VARCHAR(255),
    foreign_column VARCHAR(255),
    is_pii BOOLEAN DEFAULT FALSE,
    description TEXT,
    embedding vector(768),
    UNIQUE(tenant_id, table_name, column_name)
);

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);

-- 2. Customers Table (Decision Tree Node: membership_tier)
CREATE TABLE IF NOT EXISTS customers (
    customer_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    membership_tier VARCHAR(50) NOT NULL -- 'VIP', 'Standard'
);

-- 3. Products Table
CREATE TABLE IF NOT EXISTS products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price NUMERIC(10, 2) NOT NULL
);

-- 4. Orders Table (Process Flow Stage 1)
CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_total NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Order Items Table
CREATE TABLE IF NOT EXISTS order_items (
    item_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL DEFAULT 1
);

-- 6. Payments Table (Process Flow Stage 2)
CREATE TABLE IF NOT EXISTS payments (
    payment_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    amount NUMERIC(10, 2) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE
);

-- 7. Shipments Table (Process Flow Stage 3)
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    status VARCHAR(50) NOT NULL,
    shipped_at TIMESTAMP WITH TIME ZONE
);

-- 8. Returns Table (Process Flow Stage 4 - Optional)
CREATE TABLE IF NOT EXISTS returns (
    return_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    returned_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for performance on commonly filtered/joined columns
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_returns_order_id ON returns(order_id);
CREATE INDEX IF NOT EXISTS idx_shipments_order_id ON shipments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- ============================================================================
-- Seed Data Injection (20 Records Spread Over 6 Months)
-- ============================================================================

TRUNCATE TABLE returns, shipments, payments, order_items, orders, products, customers, users, schema_catalog, tenants RESTART IDENTITY CASCADE;

-- Insert Mock Tenant for the AI Agent
INSERT INTO tenants (id, name) VALUES ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Hackathon Demo Tenant');

-- Insert 4 Users & Customers
INSERT INTO users (email) VALUES ('alex.morgan@example.com'), ('ben.davis@example.com'), ('carol.williams@example.com'), ('david.chen@example.com');

INSERT INTO customers (user_id, name, membership_tier) VALUES
    (1, 'Alex Morgan', 'VIP'),
    (2, 'Ben Davis', 'Standard'),
    (3, 'Carol Williams', 'VIP'),
    (4, 'David Chen', 'Standard');

-- Insert 4 Products
INSERT INTO products (name, price) VALUES 
    ('Laptop Pro', 1200.00), ('Wireless Mouse', 45.00), ('Mechanical Keyboard', 150.00), ('USB-C Hub', 30.00);

-- Insert 20 Orders over 6 Months (Spanning from -180 days to today)
INSERT INTO orders (customer_id, order_total, created_at) VALUES
    -- Month 1 (6 months ago)
    (1, 150.00, NOW() - INTERVAL '175 days'), 
    (2, 45.00,  NOW() - INTERVAL '160 days'),
    (3, 1200.00, NOW() - INTERVAL '155 days'),
    -- Month 2
    (4, 30.00,  NOW() - INTERVAL '140 days'),
    (1, 120.00, NOW() - INTERVAL '130 days'),
    (2, 45.00,  NOW() - INTERVAL '125 days'),
    -- Month 3
    (3, 150.00, NOW() - INTERVAL '110 days'),
    (4, 30.00,  NOW() - INTERVAL '100 days'),
    (1, 1200.00, NOW() - INTERVAL '95 days'),
    (2, 120.00, NOW() - INTERVAL '92 days'),
    -- Month 4
    (3, 45.00,  NOW() - INTERVAL '80 days'),
    (4, 150.00, NOW() - INTERVAL '70 days'),
    (1, 30.00,  NOW() - INTERVAL '65 days'),
    -- Month 5
    (2, 1200.00, NOW() - INTERVAL '50 days'),
    (3, 120.00, NOW() - INTERVAL '40 days'),
    (4, 45.00,  NOW() - INTERVAL '35 days'),
    -- Month 6 (Recent)
    (1, 150.00, NOW() - INTERVAL '20 days'),
    (2, 30.00,  NOW() - INTERVAL '15 days'),
    (3, 1200.00, NOW() - INTERVAL '5 days'),
    (4, 120.00, NOW() - INTERVAL '2 days');

-- Insert 20 Order Items (Mapping to the orders)
INSERT INTO order_items (order_id, product_id) VALUES
    (1, 3), (2, 2), (3, 1), (4, 4), (5, 3), (6, 2), (7, 3), (8, 4), (9, 1), (10, 3),
    (11, 2), (12, 3), (13, 4), (14, 1), (15, 3), (16, 2), (17, 3), (18, 4), (19, 1), (20, 3);

-- Insert Payments (Simulating 1 to 4 hour processing delay for all orders)
INSERT INTO payments (order_id, amount, processed_at)
SELECT order_id, order_total, created_at + (RANDOM() * INTERVAL '4 hours' + INTERVAL '1 hour')
FROM orders;

-- Insert Shipments (Simulating 1 to 3 day shipping delay for all EXCEPT the last two recent orders)
INSERT INTO shipments (order_id, status, shipped_at)
SELECT order_id, 'Delivered', created_at + (RANDOM() * INTERVAL '3 days' + INTERVAL '1 day')
FROM orders
WHERE order_id <= 18;

-- The last two orders are still processing
INSERT INTO shipments (order_id, status, shipped_at) VALUES
    (19, 'Processing', NULL),
    (20, 'Processing', NULL);

-- Insert a few Returns to make the process flow interesting (Orders from months ago)
INSERT INTO returns (order_id, returned_at) VALUES
    (3, NOW() - INTERVAL '140 days'), -- Returned ~15 days after purchase
    (9, NOW() - INTERVAL '80 days'),
    (14, NOW() - INTERVAL '35 days');
