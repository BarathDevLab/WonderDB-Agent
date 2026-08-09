import React, { useState, useMemo } from 'react';
import {
  Table,
  Download,
  Search,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  Lock,
  FileSpreadsheet,
} from 'lucide-react';

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
      <div className="rounded-xl border border-zinc-800 bg-[#111216] p-6 text-center text-xs text-zinc-400">
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
    link.setAttribute('download', `database_export_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const renderCellValue = (columnName: string, value: any) => {
    if (value === null || value === undefined) {
      return <span className="text-zinc-600 italic font-mono">null</span>;
    }

    const strVal = String(value);

    // Render PII Redaction Badge
    if (strVal === '***' || strVal.includes('***') || columnName.toLowerCase().includes('ssn')) {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-zinc-800 border border-zinc-700 px-1.5 py-0.2 text-[10px] font-mono text-zinc-300">
          <Lock className="h-2.5 w-2.5 text-zinc-400" />
          MASKED
        </span>
      );
    }

    // Currency formatting
    if (
      typeof value === 'number' &&
      (columnName.includes('revenue') ||
        columnName.includes('amount') ||
        columnName.includes('price') ||
        columnName.includes('spent') ||
        columnName.includes('total'))
    ) {
      return (
        <span className="font-mono font-medium text-emerald-400">
          ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      );
    }

    // Numbers
    if (typeof value === 'number') {
      return <span className="font-mono font-medium text-zinc-200">{value.toLocaleString()}</span>;
    }

    return <span className="text-zinc-300">{strVal}</span>;
  };

  return (
    <div className="my-2.5 overflow-hidden rounded-xl border border-zinc-800 bg-[#111216]">
      {/* Table Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 bg-[#14151a] px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <FileSpreadsheet className="h-4 w-4 text-zinc-400" />
          <span className="text-xs font-semibold text-zinc-100">
            {title || 'Query Execution Results'}
          </span>
          <span className="rounded bg-zinc-800 border border-zinc-700 px-1.5 py-0.2 text-[10px] font-mono text-zinc-400">
            {filteredData.length} records
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Search Input */}
          <div className="relative flex items-center">
            <Search className="absolute left-2.5 h-3.5 w-3.5 text-zinc-500" />
            <input
              type="text"
              placeholder="Filter results..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              className="h-7 rounded-md border border-zinc-700 bg-zinc-900 pl-8 pr-2.5 text-xs text-zinc-200 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none"
            />
          </div>

          {/* Export CSV */}
          <button
            onClick={exportCsv}
            className="flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 px-2 py-1 text-xs font-medium text-zinc-200 transition-colors"
            title="Download CSV"
          >
            <Download className="h-3 w-3 text-zinc-400" />
            <span>CSV</span>
          </button>
        </div>
      </div>

      {/* Table Data Grid */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/60 font-mono text-[11px] uppercase tracking-wider text-zinc-400">
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => handleSort(col)}
                  className="cursor-pointer px-3.5 py-2 font-medium hover:text-zinc-100 transition-colors select-none"
                >
                  <div className="flex items-center gap-1.5">
                    <span>{col}</span>
                    <ArrowUpDown className="h-3 w-3 opacity-40 hover:opacity-100" />
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {paginatedData.map((row, rIdx) => (
              <tr
                key={rIdx}
                className="hover:bg-zinc-800/40 transition-colors odd:bg-zinc-900/20 even:bg-transparent"
              >
                {columns.map((col) => (
                  <td key={col} className="px-3.5 py-2 whitespace-nowrap">
                    {renderCellValue(col, row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between border-t border-zinc-800 bg-[#14151a] px-3.5 py-2 text-xs text-zinc-400">
        <div className="flex items-center gap-2">
          <span>Rows:</span>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setCurrentPage(1);
            }}
            className="rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-zinc-200 focus:outline-none cursor-pointer"
          >
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={25}>25</option>
          </select>
        </div>

        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px]">
            Page {currentPage} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="flex h-6 w-6 items-center justify-center rounded border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="h-3 w-3" />
            </button>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="flex h-6 w-6 items-center justify-center rounded border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
