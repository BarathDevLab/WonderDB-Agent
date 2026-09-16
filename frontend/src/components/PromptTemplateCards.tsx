import React, { useState } from 'react';
import {
  TrendingUp,
  BarChart3,
  PieChart,
  GitFork,
  Layers,
  Network,
  Truck,
  Sparkles,
  ArrowUpRight,
  Table,
  Users,
  Package,
} from 'lucide-react';

export interface PromptTemplate {
  id: string;
  title: string;
  description: string;
  prompt: string;
  category: 'revenue' | 'customers' | 'fulfillment' | 'products' | 'architecture';
  tables: string[];
  outputType: string;
  outputBadgeColor: string;
  icon: React.ComponentType<{ className?: string }>;
  accentColor: string;
}

export const SCHEMA_PROMPT_TEMPLATES: PromptTemplate[] = [
  {
    id: 'monthly-revenue-trend',
    title: 'Monthly Revenue Growth',
    description: 'Analyze revenue momentum over the last 6 months with monthly sales aggregates.',
    prompt: 'Analyze monthly revenue over the last 6 months. Display the monthly trend as a line chart and summarize the growth.',
    category: 'revenue',
    tables: ['orders'],
    outputType: 'Line Chart',
    outputBadgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    icon: TrendingUp,
    accentColor: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  },
  {
    id: 'customer-journey-flow',
    title: 'Order Fulfillment Process Flow',
    description: 'Trace customer orders from placement, payment, shipment to delivery or return.',
    prompt: "Based on our historical data, map out the customer order fulfillment journey from order placement, payment, shipment to delivery or return. Generate a process flow diagram.",
    category: 'fulfillment',
    tables: ['orders', 'payments', 'shipments', 'returns'],
    outputType: 'Process Flow',
    outputBadgeColor: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    icon: Network,
    accentColor: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  },
  {
    id: 'top-vip-customers',
    title: 'VIP vs Standard Customers',
    description: 'Compare top spending patrons across membership tiers with contact details masked.',
    prompt: 'List our top spending customers, comparing VIP vs Standard membership tiers, including their names and masked contact emails.',
    category: 'customers',
    tables: ['customers', 'users', 'orders'],
    outputType: 'Bar Chart + PII',
    outputBadgeColor: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    icon: Users,
    accentColor: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  },
  {
    id: 'database-er-diagram',
    title: 'Database ER Diagram',
    description: 'Inspect full structural schema relationships, foreign keys, and cardinalities.',
    prompt: 'Draw the complete Entity-Relationship (ER) diagram showing all tables, primary keys, foreign keys, and relationships in our database.',
    category: 'architecture',
    tables: ['schema_catalog', 'tenants'],
    outputType: 'ER Diagram',
    outputBadgeColor: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    icon: Layers,
    accentColor: 'text-violet-400 bg-violet-500/10 border-violet-500/20',
  },
  {
    id: 'order-amount-iqr-outliers',
    title: 'Order Amount Outliers (IQR)',
    description: 'Identify statistical anomalies and high-value orders using interquartile range.',
    prompt: 'Analyze the distribution of order amounts over the last 6 months. Identify any statistical outliers using IQR and tell me which products contributed most.',
    category: 'revenue',
    tables: ['orders', 'order_items', 'products'],
    outputType: 'IQR Outliers',
    outputBadgeColor: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    icon: BarChart3,
    accentColor: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  },
  {
    id: 'product-revenue-share',
    title: 'Product Revenue Breakdown',
    description: 'Measure catalog sales volume and revenue contributions by product unit.',
    prompt: 'Which products are our biggest contributors to total revenue? Show the breakdown as a pie chart.',
    category: 'products',
    tables: ['products', 'order_items'],
    outputType: 'Pie Chart',
    outputBadgeColor: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    icon: PieChart,
    accentColor: 'text-rose-400 bg-rose-500/10 border-rose-500/20',
  },
  {
    id: 'shipment-status-breakdown',
    title: 'Shipment Delivery Health',
    description: 'Track active processing shipments vs delivered items and logistics health.',
    prompt: 'Show the distribution of shipment statuses across all orders and calculate delivery performance.',
    category: 'fulfillment',
    tables: ['shipments'],
    outputType: 'Status Distribution',
    outputBadgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    icon: Truck,
    accentColor: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  },
  {
    id: 'customer-decision-tree',
    title: 'Customer Decision Tree',
    description: 'Model customer purchasing behavior and likelihood paths based on tiers.',
    prompt: 'Generate a decision tree flowchart showing customer ordering paths and outcome probabilities based on membership tier.',
    category: 'architecture',
    tables: ['customers', 'orders'],
    outputType: 'Decision Tree',
    outputBadgeColor: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    icon: GitFork,
    accentColor: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  },
];

type CategoryFilter = 'all' | 'revenue' | 'customers' | 'fulfillment' | 'products' | 'architecture';

interface CategoryTab {
  key: CategoryFilter;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const CATEGORY_TABS: CategoryTab[] = [
  { key: 'all', label: 'All Schemas', icon: Sparkles },
  { key: 'revenue', label: 'Revenue & Orders', icon: TrendingUp },
  { key: 'customers', label: 'Customers', icon: Users },
  { key: 'fulfillment', label: 'Fulfillment & Returns', icon: Truck },
  { key: 'products', label: 'Products', icon: Package },
  { key: 'architecture', label: 'ERD & Models', icon: Layers },
];

interface PromptTemplateCardsProps {
  onSelectPrompt: (prompt: string) => void;
  disabled?: boolean;
}

export const PromptTemplateCards: React.FC<PromptTemplateCardsProps> = ({
  onSelectPrompt,
  disabled = false,
}) => {
  const [activeCategory, setActiveCategory] = useState<CategoryFilter>('all');

  const filteredTemplates = SCHEMA_PROMPT_TEMPLATES.filter((t) => {
    if (activeCategory === 'all') return true;
    return t.category === activeCategory;
  });

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4 my-2">
      {/* Category Pills Header */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none justify-start sm:justify-center">
        {CATEGORY_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeCategory === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveCategory(tab.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all shrink-0 ${
                isActive
                  ? 'bg-zinc-200 text-zinc-900 shadow-sm'
                  : 'bg-[#1e1f20]/80 text-zinc-400 hover:text-zinc-200 hover:bg-[#282a2d]'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {filteredTemplates.map((template) => {
          const Icon = template.icon;
          return (
            <button
              key={template.id}
              type="button"
              disabled={disabled}
              onClick={() => onSelectPrompt(template.prompt)}
              className="group relative flex flex-col justify-between text-left p-3.5 rounded-xl border border-zinc-800/80 bg-[#1a1b1e]/90 hover:bg-[#222428] hover:border-zinc-700/80 transition-all duration-150 shadow-sm hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <div className="space-y-2 w-full">
                {/* Header: Icon + Title + Arrow */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className={`flex h-7 w-7 items-center justify-center rounded-lg border ${template.accentColor}`}>
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-xs font-semibold text-zinc-100 group-hover:text-white transition-colors">
                      {template.title}
                    </span>
                  </div>
                  <div className="flex h-5 w-5 items-center justify-center rounded-full text-zinc-500 group-hover:text-emerald-400 group-hover:bg-emerald-500/10 transition-colors shrink-0">
                    <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                  </div>
                </div>

                {/* Description */}
                <p className="text-[11px] text-zinc-400 line-clamp-2 leading-relaxed pl-0.5">
                  {template.description}
                </p>
              </div>

              {/* Footer Badges: Schema Tables + Output Badge */}
              <div className="mt-3 pt-2.5 border-t border-zinc-800/60 flex items-center justify-between gap-2 text-[10px] w-full">
                {/* Tables used */}
                <div className="flex items-center gap-1 overflow-hidden">
                  <Table className="h-2.5 w-2.5 text-zinc-500 shrink-0" />
                  <span className="font-mono text-zinc-400 truncate">
                    {template.tables.join(', ')}
                  </span>
                </div>

                {/* Output capability badge */}
                <span
                  className={`shrink-0 px-2 py-0.5 rounded-md border font-medium text-[9.5px] ${template.outputBadgeColor}`}
                >
                  {template.outputType}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
