import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app.config import get_settings
from db.postgres import PostgresPool
from services.schema_rag import sync_schema_catalog

ACME_TENANT = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
GLOBEX_TENANT = "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"

async def main():
    settings = get_settings()
    pool = PostgresPool(settings)
    await pool.connect()

    async with pool.acquire() as conn:
        print("[1/2] Seeding order_items for Acme Corporation...")
        # Order 1 (1250.00): 1x Enterprise Analytics Suite (1250.00)
        # Order 2 (450.00):  1x Cloud Storage Pro (450.00)
        # Order 3 (3100.00): 2x Enterprise Analytics Suite (2500.00) + 1x Cloud Storage + items (600.00)
        await conn.execute("""
            INSERT INTO order_items (id, tenant_id, order_id, product_id, quantity, unit_price)
            VALUES
                ('d0010000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0010000-0000-0000-0000-000000000001', 'e0010000-0000-0000-0000-000000000001', 1, 1250.00),
                ('d0020000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0020000-0000-0000-0000-000000000002', 'e0020000-0000-0000-0000-000000000002', 1, 450.00),
                ('d0030000-0000-0000-0000-000000000003', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0030000-0000-0000-0000-000000000003', 'e0010000-0000-0000-0000-000000000001', 2, 1250.00),
                ('d0040000-0000-0000-0000-000000000004', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'f0030000-0000-0000-0000-000000000003', 'e0020000-0000-0000-0000-000000000002', 1, 600.00)
            ON CONFLICT DO NOTHING;
        """)
        print("[OK] order_items seeded successfully.")

        print("[2/2] Synchronizing complete 1536-d schema_catalog embeddings across all tenants...")
        for tenant in [ACME_TENANT, GLOBEX_TENANT]:
            n = await sync_schema_catalog(tenant, pool)
            print(f"      Tenant {tenant[:8]}... synced {n} column vector embeddings.")

    await pool.disconnect()
    print("\nDatabase fixtures and pgvector catalog fully refreshed!")

if __name__ == "__main__":
    asyncio.run(main())
