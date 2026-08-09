import React, { useState } from 'react';
import { X, Layers, Table, Key, Lock, ChevronDown, ChevronRight, Hash, ArrowRight } from 'lucide-react';
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
  const [expandedTable, setExpandedTable] = useState<string>('customers');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity">
      <div className="flex h-full w-full max-w-md flex-col border-l border-white/10 bg-[#090d19] shadow-2xl">
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-white/[0.08] bg-[#0c1222] px-5 py-4">
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-cyan-400" />
            <div>
              <h2 className="font-display text-sm font-bold text-white">Schema Catalog Explorer</h2>
              <p className="text-[11px] text-slate-400">pgvector Embedding & RLS Relational Map</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tables List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {DATABASE_SCHEMA.map((table) => {
            const isExpanded = expandedTable === table.table_name;

            return (
              <div
                key={table.table_name}
                className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#0d1424] transition-all"
              >
                <button
                  onClick={() => setExpandedTable(isExpanded ? '' : table.table_name)}
                  className="flex w-full items-center justify-between p-3.5 text-left hover:bg-slate-800/40 transition-colors"
                >
                  <div className="flex items-center gap-2.5">
                    <Table className="h-4 w-4 text-cyan-400" />
                    <div>
                      <span className="font-mono text-xs font-bold text-white">
                        {table.table_name}
                      </span>
                      <p className="text-[10px] text-slate-400">{table.columns.length} columns</p>
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-slate-400" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-slate-400" />
                  )}
                </button>

                {isExpanded && (
                  <div className="border-t border-white/[0.06] bg-[#070a14] p-3 text-xs">
                    <p className="mb-3 text-[11px] text-slate-400 italic">{table.description}</p>
                    <div className="space-y-1.5">
                      {table.columns.map((col) => (
                        <div
                          key={col.name}
                          className="flex items-center justify-between rounded-lg bg-slate-900/60 px-2.5 py-1.5 font-mono text-[11px]"
                        >
                          <div className="flex items-center gap-1.5">
                            {col.is_pk ? (
                              <span title="Primary Key">
                                <Key className="h-3 w-3 text-amber-400" />
                              </span>
                            ) : (
                              <Hash className="h-3 w-3 text-slate-500" />
                            )}
                            <span className="font-semibold text-slate-200">{col.name}</span>
                          </div>

                          <div className="flex items-center gap-1.5">
                            {col.is_pii && (
                              <span className="flex items-center gap-0.5 rounded bg-rose-950/60 border border-rose-500/30 px-1.5 py-0.2 text-[9px] font-bold text-rose-300">
                                <Lock className="h-2.5 w-2.5" />
                                PII
                              </span>
                            )}

                            {col.foreign_table && (
                              <span className="flex items-center gap-0.5 rounded bg-indigo-950/60 border border-indigo-500/30 px-1.5 py-0.2 text-[9px] text-indigo-300">
                                <ArrowRight className="h-2 w-2" />
                                {col.foreign_table}
                              </span>
                            )}

                            <span className="text-[10px] text-cyan-400/80">{col.type}</span>
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
        <div className="border-t border-white/[0.08] bg-[#0c1222] p-4 text-[11px] text-slate-400">
          <div className="flex items-center gap-1.5 text-cyan-400 font-semibold mb-1">
            <span>Live pgvector Search Active</span>
          </div>
          Cosine distance (`&lt;=&gt;`) dynamically matches natural language queries to relevant schema entities.
        </div>
      </div>
    </div>
  );
};
