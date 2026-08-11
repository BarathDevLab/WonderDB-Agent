import React from 'react';
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
import { BarChart3, TrendingUp, PieChart } from 'lucide-react';
import { ChartSpec } from '../types';

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
  if (!spec || !spec.data || spec.type === 'table') {
    return null;
  }

  const chartType = spec.type || 'bar';

  // Professional Enterprise Theme Colors (Cobalt, Emerald, Amber, Slate)
  const enhancedData = {
    ...spec.data,
    datasets: (spec.data.datasets || []).map((ds, idx) => {
      const isLine = chartType === 'line';
      const colors = [
        { border: '#3b82f6', bg: isLine ? 'rgba(59, 130, 246, 0.12)' : '#3b82f6' },
        { border: '#10b981', bg: isLine ? 'rgba(16, 185, 129, 0.12)' : '#10b981' },
        { border: '#f59e0b', bg: isLine ? 'rgba(245, 158, 11, 0.12)' : '#f59e0b' },
      ];
      const theme = colors[idx % colors.length];

      return {
        ...ds,
        borderColor: ds.borderColor || theme.border,
        backgroundColor:
          ds.backgroundColor ||
          (chartType === 'doughnut' || chartType === 'pie'
            ? ['#3b82f6', '#10b981', '#f59e0b', '#6366f1', '#ec4899']
            : theme.bg),
        borderWidth: ds.borderWidth || (isLine ? 2 : 0),
        borderRadius: chartType === 'bar' ? 4 : 0,
        tension: 0.3,
        fill: isLine,
        pointBackgroundColor: '#3b82f6',
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
        display: !!spec.options?.plugins?.title?.text,
        text: spec.options?.plugins?.title?.text || '',
        color: '#f4f4f5',
        font: { family: 'Space Grotesk', size: 13, weight: '600' },
        padding: { bottom: 12 },
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
              ticks: { color: '#71717a', font: { family: 'JetBrains Mono', size: 10 } },
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

  return (
    <div className="my-2.5 rounded-xl border border-zinc-800 bg-[#111216] p-3.5">
      <div className="flex items-center justify-between gap-2 mb-3 border-b border-zinc-800 pb-2">
        <div className="flex items-center gap-2">
          {getChartIcon()}
          <span className="text-xs font-semibold text-zinc-200">
            {spec.options?.plugins?.title?.text || `${chartType.toUpperCase()} Visualization`}
          </span>
        </div>
        <span className="rounded bg-zinc-800 px-1.5 py-0.2 text-[9px] font-mono text-zinc-400 uppercase">
          {chartType}
        </span>
      </div>

      <div className="h-60 sm:h-64 w-full">
        {chartType === 'line' && <Line data={enhancedData} options={chartOptions} />}
        {chartType === 'bar' && <Bar data={enhancedData} options={chartOptions} />}
        {chartType === 'doughnut' && <Doughnut data={enhancedData} options={chartOptions} />}
        {chartType === 'pie' && <Pie data={enhancedData} options={chartOptions} />}
        {chartType === 'scatter' && <Scatter data={enhancedData} options={chartOptions} />}
      </div>
    </div>
  );
};
