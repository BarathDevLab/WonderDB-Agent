import React, { useState, useMemo } from 'react';
import { Table, Download, Search, ChevronLeft, ChevronRight, ArrowUpDown, Lock } from 'lucide-react';

interface DataGridProps {
  data: Record<string, any>[];
  title?: string;
}

export const DataGrid: React.FC<DataGridProps> = ({ data, title }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);

  if (!data || data.length === 0) {
    return (
      <div className="rounded-xl border border-white/[0.08] bg-[#090d19] p-6 text-center text-xs text-slate-400">
        No records returned for this query.
      </div>
    );
  }

  const columns = Object.keys(data[0]);

  // Filtering
  const filteredData = useMemo(() => {
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter((row) =>
      columns.some((col) => {
        const val = row[col];
        return val !== null && val !== undefined && String(val).toLowerCase().includes(term);
      })
    );
  }, [data, searchTerm, columns]);

  // Sorting
  const sortedData = useMemo(() => {
    if (!sortColumn) return filteredData;
    return [...filteredData].sort((a, b) => {
      const valA = a[sortColumn];
      const valB = b[sortColumn];
      if (valA === valB) return 0;
      if (valA === null || valA === undefined) return 1;
      if (valB === null || valB === undefined) return -1;
      const res = valA < valB ? -1 : 1;
      return sortDirection === 'asc' ? res : -res;
    });
  }, [filteredData, sortColumn, sortDirection]);

  // Pagination
  const totalPages = Math.ceil(sortedData.length / pageSize) || 1;
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, currentPage, pageSize]);

  const handleSort = (col: string) => {
    if (sortColumn === col) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(col);
      setSortDirection('asc');
    }
  };

  const exportCsv = () => {
    const header = columns.join(',');
    const rows = sortedData.map((row) =>
      columns
        .map((col) => {
          let val = row[col];
          if (val === null || val === undefined) val = '';
          const str = String(val).replace(/"/g, '""');
          return `"${str}"`;
        })
        .join(',')
    );
    const csvContent = 'data:text/csv;charset=utf-8,' + [header, ...rows].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `query_export_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const renderCellValue = (columnName: string, value: any) => {
    if (value === null || value === undefined) {
      return <span className="text-slate-600 italic">null</span>;
    }

    const strVal = String(value);

    // Render PII Redaction Badge
    if (strVal === '***' || strVal.includes('***') || columnName.toLowerCase().includes('ssn')) {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-rose-950/50 border border-rose-500/30 px-2 py-0.5 text-[11px] font-mono text-rose-300">
          <Lock className="h-2.5 w-2.5" />
          PII MASKED
        </span>
      );
    }

    // Numbers & currency formatting
    if (typeof value === 'number' && (columnName.includes('revenue') || columnName.includes('amount') || columnName.includes('price') || columnName.includes('spent'))) {
      return (
        <span className="font-mono font-medium text-emerald-400">
          ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      );
    }

    if (typeof value === 'number') {
      return <span className="font-mono text-cyan-300">{value.toLocaleString()}</span>;
    }

    return <span className="text-slate-200">{strVal}</span>;
  };

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-white/[0.08] bg-[#090d18] shadow-lg">
      {/* Table Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] bg-[#0d1424] px-4 py-3">
        <div className="flex items-center gap-2">
          <Table className="h-4 w-4 text-cyan-400" />
          <span className="font-display text-xs sm:text-sm font-bold text-white">
            {title || 'Query Execution Results'}
          </span>
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-300">
            {filteredData.length} records
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Search Input */}
          <div className="relative flex items-center">
            <Search className="absolute left-2.5 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search table rows..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              className="h-8 rounded-lg border border-white/10 bg-slate-900/90 pl-8 pr-3 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            />
          </div>

          {/* Export CSV */}
          <button
            onClick={exportCsv}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-slate-800 hover:bg-slate-700 px-2.5 py-1.5 text-xs font-medium text-slate-200 transition-all active:scale-95"
            title="Download CSV"
          >
            <Download className="h-3.5 w-3.5 text-cyan-400" />
            <span className="hidden sm:inline">Export CSV</span>
          </button>
        </div>
      </div>

      {/* Table Data Grid */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-white/[0.06] bg-slate-900/60 font-mono text-[11px] uppercase tracking-wider text-slate-400">
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => handleSort(col)}
                  className="cursor-pointer px-4 py-2.5 font-semibold hover:text-white transition-colors select-none"
                >
                  <div className="flex items-center gap-1.5">
                    <span>{col}</span>
                    <ArrowUpDown className="h-3 w-3 opacity-50 hover:opacity-100" />
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {paginatedData.map((row, rIdx) => (
              <tr
                key={rIdx}
                className="hover:bg-cyan-950/15 transition-colors odd:bg-slate-900/20 even:bg-transparent"
              >
                {columns.map((col) => (
                  <td key={col} className="px-4 py-2.5 whitespace-nowrap">
                    {renderCellValue(col, row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between border-t border-white/[0.06] bg-[#0c1220] px-4 py-2.5 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <span>Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setCurrentPage(1);
            }}
            className="rounded border border-white/10 bg-slate-900 px-1.5 py-0.5 text-white focus:outline-none"
          >
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={25}>25</option>
          </select>
        </div>

        <div className="flex items-center gap-3">
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="flex h-7 w-7 items-center justify-center rounded border border-white/10 bg-slate-900 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="flex h-7 w-7 items-center justify-center rounded border border-white/10 bg-slate-900 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
