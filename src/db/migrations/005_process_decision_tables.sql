-- Migration 005: Process Flow and Decision Tree Tables

CREATE TABLE IF NOT EXISTS order_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    previous_status VARCHAR(50),
    new_status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS loan_applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    credit_score INTEGER NOT NULL,
    income NUMERIC(10, 2) NOT NULL,
    debt NUMERIC(10, 2) NOT NULL,
    decision_status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Performance and FK Indexes
CREATE INDEX IF NOT EXISTS idx_order_events_tenant_id ON order_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_order_events_order_id ON order_events(order_id);
CREATE INDEX IF NOT EXISTS idx_loan_applications_tenant_id ON loan_applications(tenant_id);
CREATE INDEX IF NOT EXISTS idx_loan_applications_customer_id ON loan_applications(customer_id);

-- Row Level Security (RLS) policies
ALTER TABLE order_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_order_events ON order_events
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::uuid);

ALTER TABLE loan_applications ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_loan_applications ON loan_applications
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::uuid);
