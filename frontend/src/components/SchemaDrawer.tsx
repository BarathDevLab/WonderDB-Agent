import React, { useState, useMemo } from 'react';
import {
  X,
  Layers,
  Table,
  Key,
  Lock,
  ChevronDown,
  ChevronRight,
  Hash,
  ArrowRight,
  Search,
  Database,
} from 'lucide-react';
import { TableMetadata } from '../types';

interface SchemaDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

const DATABASE_SCHEMA: TableMetadata[] = [
  {
    table_name: 'customers',
    description: 'Enterprise tenant customer profiles with privacy masking',
    columns: [
      { name: 'id', type: 'UUID', is_pk: true },
      { name: 'tenant_id', type: 'UUID' },
      { name: 'full_name', type: 'VARCHAR(255)' },
      { name: 'email', type: 'VARCHAR(255)', is_pii: true },
      { name: 'ssn', type: 'VARCHAR(11)', is_pii: true },
      { name: 'created_at', type: 'TIMESTAMPTZ' },
    ],
  },
  {
    table_name: 'orders',
    description: 'Customer purchase transactions and order fulfillment records',
    columns: [
      { name: 'id', type: 'UUID', is_pk: true },
      { name: 'tenant_id', type: 'UUID' },
      { name: 'customer_id', type: 'UUID', foreign_table: 'customers', foreign_column: 'id' },
      { name: 'total_amount', type: 'NUMERIC(12,2)' },
      { name: 'status', type: 'VARCHAR(50)' },
      { name: 'created_at', type: 'TIMESTAMPTZ' },
    ],
  },
  {
    table_name: 'products',
    description: 'Product catalog, pricing, SKU identifier, and category metadata',
    columns: [
      { name: 'id', type: 'UUID', is_pk: true },
      { name: 'tenant_id', type: 'UUID' },
      { name: 'sku', type: 'VARCHAR(100)' },
      { name: 'name', type: 'VARCHAR(255)' },
      { name: 'category', type: 'VARCHAR(100)' },
      { name: 'price', type: 'NUMERIC(10,2)' },
      { name: 'created_at', type: 'TIMESTAMPTZ' },
    ],
  },
  {
    table_name: 'order_items',
    description: 'Line item breakdown linking orders to specific product units',
    columns: [
      { name: 'id', type: 'UUID', is_pk: true },
      { name: 'tenant_id', type: 'UUID' },
      { name: 'order_id', type: 'UUID', foreign_table: 'orders', foreign_column: 'id' },
      { name: 'product_id', type: 'UUID', foreign_table: 'products', foreign_column: 'id' },
      { name: 'quantity', type: 'INTEGER' },
      { name: 'unit_price', type: 'NUMERIC(10,2)' },
    ],
  },
  {
    table_name: 'schema_catalog',
    description: 'Dense 1536-d vector catalog used for live Schema RAG embeddings',
    columns: [
      { name: 'id', type: 'UUID', is_pk: true },
      { name: 'tenant_id', type: 'UUID' },
      { name: 'table_name', type: 'VARCHAR(255)' },
      { name: 'column_name', type: 'VARCHAR(255)' },
      { name: 'data_type', type: 'VARCHAR(100)' },
      { name: 'is_sensitive', type: 'BOOLEAN' },
      { name: 'embedding', type: 'VECTOR(1536)' },
    ],
  },
];

export const SchemaDrawer: React.FC<SchemaDrawerProps> = ({ isOpen, onClose }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({
    customers: true,
    orders: true,
  });

  const toggleTable = (tableName: string) => {
    setExpandedTables((prev) => ({ ...prev, [tableName]: !prev[tableName] }));
  };

  const filteredSchema = useMemo(() => {
    if (!searchQuery.trim()) return DATABASE_SCHEMA;
    const q = searchQuery.toLowerCase();
    return DATABASE_SCHEMA.filter(
      (t) =>
        t.table_name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.columns.some((c) => c.name.toLowerCase().includes(q) || c.type.toLowerCase().includes(q))
    );
  }, [searchQuery]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity">
      <div className="flex h-full w-full max-w-md flex-col border-l border-zinc-800 bg-[#0d0e12] shadow-2xl animate-fadeIn">
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 bg-[#111216] px-4 py-3.5">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-zinc-400" />
            <div>
              <h2 className="text-xs font-semibold text-zinc-100">Schema RAG Catalog</h2>
              <p className="text-[10px] text-zinc-400">1536-d pgvector relational embeddings</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Search */}
        <div className="p-3 border-b border-zinc-800">
          <div className="relative flex items-center">
            <Search className="absolute left-2.5 h-3.5 w-3.5 text-zinc-500" />
            <input
              type="text"
              placeholder="Search tables, columns, or data types..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 pl-8 pr-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Tables List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {filteredSchema.map((table) => {
            const isExpanded = !!expandedTables[table.table_name];

            return (
              <div
                key={table.table_name}
                className="overflow-hidden rounded-lg border border-zinc-800 bg-[#121318]"
              >
                <button
                  onClick={() => toggleTable(table.table_name)}
                  className="flex w-full items-center justify-between p-2.5 text-left hover:bg-zinc-800/40 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Table className="h-3.5 w-3.5 text-zinc-400" />
                    <div>
                      <span className="font-mono text-xs font-semibold text-zinc-200">
                        {table.table_name}
                      </span>
                      <p className="text-[10px] text-zinc-500">{table.columns.length} columns</p>
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-zinc-500" />
                  )}
                </button>

                {isExpanded && (
                  <div className="border-t border-zinc-800/60 bg-[#090a0d] p-2.5 text-xs">
                    <p className="mb-2 text-[11px] text-zinc-400 leading-relaxed">
                      {table.description}
                    </p>
                    <div className="space-y-1">
                      {table.columns.map((col) => (
                        <div
                          key={col.name}
                          className="flex items-center justify-between rounded bg-zinc-900 px-2 py-1 font-mono text-[11px]"
                        >
                          <div className="flex items-center gap-1.5">
                            {col.is_pk ? (
                              <Key className="h-3 w-3 text-amber-400" />
                            ) : (
                              <Hash className="h-3 w-3 text-zinc-600" />
                            )}
                            <span className="font-medium text-zinc-200">{col.name}</span>
                          </div>

                          <div className="flex items-center gap-1.5">
                            {col.is_pii && (
                              <span className="flex items-center gap-0.5 rounded bg-zinc-800 border border-zinc-700 px-1 py-0.2 text-[9px] font-mono text-zinc-300">
                                <Lock className="h-2 w-2 text-zinc-400" />
                                PII
                              </span>
                            )}

                            {col.foreign_table && (
                              <span className="flex items-center gap-0.5 text-[9px] text-zinc-400">
                                <ArrowRight className="h-2 w-2" />
                                {col.foreign_table}
                              </span>
                            )}

                            <span className="text-[10px] text-zinc-400">{col.type}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer info */}
        <div className="border-t border-zinc-800 bg-[#111216] p-3 text-[11px] text-zinc-400">
          <div className="flex items-center gap-1.5 text-zinc-300 font-medium mb-0.5">
            <Database className="h-3.5 w-3.5 text-zinc-400" />
            <span>Live pgvector Vector Search Active</span>
          </div>
          Cosine distance dynamically matches natural language questions to schema attributes.
        </div>
      </div>
    </div>
  );
};
