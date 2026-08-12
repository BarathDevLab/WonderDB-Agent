import React, { useRef, useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  ScatterController,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Bar, Line, Doughnut, Pie, Scatter } from 'react-chartjs-2';
import { BarChart3, Download, Maximize2, TrendingUp, PieChart } from 'lucide-react';
import { ChartSpec } from '../types';
import { VisualizationModal } from './VisualizationModal';
import { downloadCanvasAsPng } from '../utils/visualizationExport';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  ScatterController,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface ChartViewerProps {
  spec: ChartSpec;
}

export const ChartViewer: React.FC<ChartViewerProps> = ({ spec }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const inlineChartRef = useRef<HTMLDivElement>(null);
  const expandedChartRef = useRef<HTMLDivElement>(null);

  if (!spec || !spec.data || spec.type === 'table') {
    return null;
  }

  const chartType = spec.type || 'bar';

  // Professional Enterprise Theme Colors (Emerald, Cobalt, Amber, Slate)
  const enhancedData = {
    ...spec.data,
    datasets: (spec.data.datasets || []).map((ds, idx) => {
      const isLine = chartType === 'line';
      const colors = [
        { border: '#10b981', bg: isLine ? 'rgba(16, 185, 129, 0.2)' : '#10b981' }, // Emerald (Primary)
        { border: '#3b82f6', bg: isLine ? 'rgba(59, 130, 246, 0.2)' : '#3b82f6' }, // Blue
        { border: '#f59e0b', bg: isLine ? 'rgba(245, 158, 11, 0.2)' : '#f59e0b' }, // Amber
      ];
      const theme = colors[idx % colors.length];

      return {
        ...ds,
        borderColor: theme.border, // Force theme colors over backend defaults for a cohesive UI
        backgroundColor:
          chartType === 'doughnut' || chartType === 'pie'
            ? ['#10b981', '#3b82f6', '#f59e0b', '#6366f1', '#ec4899']
            : theme.bg,
        borderWidth: isLine ? 2 : 0,
        borderRadius: chartType === 'bar' ? 4 : 0,
        tension: 0.4, // Smoother curves
        fill: isLine,
        pointBackgroundColor: theme.border,
        pointBorderColor: '#18181b',
        pointRadius: 3,
        pointHoverRadius: 5,
      };
    }),
  };

  const chartOptions: any = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
        labels: {
          color: '#a1a1aa',
          font: { family: 'Plus Jakarta Sans', size: 11, weight: '500' },
          boxWidth: 10,
        },
      },
      title: {
        display: false, // We have a custom HTML header, so hide the canvas title
      },
      tooltip: {
        backgroundColor: '#18181b',
        titleColor: '#f4f4f5',
        bodyColor: '#a1a1aa',
        borderColor: '#27272a',
        borderWidth: 1,
        padding: 8,
        cornerRadius: 6,
      },
    },
    scales:
      chartType === 'pie' || chartType === 'doughnut'
        ? undefined
        : {
            x: {
              grid: { color: 'rgba(255, 255, 255, 0.04)' },
              ticks: { 
                color: '#71717a', 
                font: { family: 'JetBrains Mono', size: 10 },
                maxRotation: 45,
                callback: function(this: any, value: any) {
                  const label = this.getLabelForValue(value);
                  if (typeof label === 'string' && label.match(/^\d{4}-\d{2}-\d{2}/)) {
                    const date = new Date(label);
                    if (!isNaN(date.getTime())) {
                      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
                    }
                  }
                  return label;
                }
              },
            },
            y: {
              grid: { color: 'rgba(255, 255, 255, 0.04)' },
              ticks: { color: '#71717a', font: { family: 'JetBrains Mono', size: 10 } },
            },
          },
  };

  const getChartIcon = () => {
    if (chartType === 'line') return <TrendingUp className="h-4 w-4 text-zinc-400" />;
    if (chartType === 'doughnut' || chartType === 'pie') return <PieChart className="h-4 w-4 text-zinc-400" />;
    return <BarChart3 className="h-4 w-4 text-zinc-400" />;
  };

  const title = spec.options?.plugins?.title?.text || `${chartType.toUpperCase()} Visualization`;

  const handleDownload = () => {
    const root = isExpanded ? expandedChartRef.current : inlineChartRef.current;
    const canvas = root?.querySelector('canvas');
    if (!canvas) return;
    downloadCanvasAsPng(canvas, title);
  };

  const renderChart = (options: any = chartOptions) => (
    <>
      {chartType === 'line' && <Line data={enhancedData} options={options} />}
      {chartType === 'bar' && <Bar data={enhancedData} options={options} />}
      {chartType === 'doughnut' && <Doughnut data={enhancedData} options={options} />}
      {chartType === 'pie' && <Pie data={enhancedData} options={options} />}
      {chartType === 'scatter' && <Scatter data={enhancedData} options={options} />}
    </>
  );

  return (
    <div className="mt-4 mb-2 rounded-2xl overflow-hidden bg-[#1e1f20] border border-zinc-800/50 shadow-md max-w-4xl">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800/50 bg-[#1e1f20]">
        <div className="flex items-center gap-2">
          {getChartIcon()}
          <span className="text-[13px] font-semibold text-zinc-300">
            {title}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="rounded bg-zinc-800/50 px-2 py-0.5 text-[10px] font-mono text-zinc-400 uppercase">
            {chartType}
          </span>
          <button
            type="button"
            onClick={handleDownload}
            className="rounded p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            aria-label={`Download ${title} as PNG`}
            title="Download PNG"
          >
            <Download className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setIsExpanded(true)}
            className="rounded p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            aria-label={`Expand ${title}`}
            title="Open larger canvas"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div ref={inlineChartRef} className="h-60 sm:h-64 w-full p-4">
        {renderChart()}
      </div>

      <VisualizationModal
        open={isExpanded}
        title={title}
        onClose={() => setIsExpanded(false)}
        onDownload={handleDownload}
      >
        {(zoom) => (
          <div
            ref={expandedChartRef}
            className="mx-auto rounded-xl border border-zinc-800 bg-[#1e1f20] p-5 shadow-2xl"
            style={{
              width: `${zoom * 100}%`,
              height: `${zoom * 72}vh`,
            }}
          >
            {renderChart({ ...chartOptions, animation: false })}
          </div>
        )}
      </VisualizationModal>
    </div>
  );
};
