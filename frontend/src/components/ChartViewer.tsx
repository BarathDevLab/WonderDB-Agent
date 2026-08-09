import React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Bar, Line, Doughnut, Pie } from 'react-chartjs-2';
import { BarChart3, TrendingUp, PieChart } from 'lucide-react';
import { ChartSpec } from '../types';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
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

  // Ensure high-craft obsidian styling on datasets
  const enhancedData = {
    ...spec.data,
    datasets: (spec.data.datasets || []).map((ds, idx) => {
      const isLine = chartType === 'line';
      const colors = [
        { border: '#06b6d4', bg: isLine ? 'rgba(6, 182, 212, 0.15)' : 'rgba(6, 182, 212, 0.7)' },
        { border: '#8b5cf6', bg: isLine ? 'rgba(139, 92, 246, 0.15)' : 'rgba(139, 92, 246, 0.7)' },
        { border: '#10b981', bg: isLine ? 'rgba(16, 185, 129, 0.15)' : 'rgba(16, 185, 129, 0.7)' },
      ];
      const theme = colors[idx % colors.length];

      return {
        ...ds,
        borderColor: ds.borderColor || theme.border,
        backgroundColor: ds.backgroundColor || (chartType === 'doughnut' || chartType === 'pie'
          ? ['rgba(6, 182, 212, 0.75)', 'rgba(139, 92, 246, 0.75)', 'rgba(16, 185, 129, 0.75)', 'rgba(245, 158, 11, 0.75)']
          : theme.bg),
        borderWidth: ds.borderWidth || 2,
        tension: 0.35,
        fill: isLine,
        pointBackgroundColor: '#06b6d4',
        pointBorderColor: '#ffffff',
        pointRadius: 4,
        pointHoverRadius: 6,
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
          color: '#94a3b8',
          font: { family: 'Plus Jakarta Sans', size: 11, weight: 'bold' },
        },
      },
      title: {
        display: !!spec.options?.plugins?.title?.text,
        text: spec.options?.plugins?.title?.text || '',
        color: '#f8fafc',
        font: { family: 'Space Grotesk', size: 14, weight: 'bold' },
        padding: { bottom: 12 },
      },
      tooltip: {
        backgroundColor: '#0c1322',
        titleColor: '#06b6d4',
        bodyColor: '#f8fafc',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
      },
    },
    scales:
      chartType === 'pie' || chartType === 'doughnut'
        ? undefined
        : {
            x: {
              grid: { color: 'rgba(255, 255, 255, 0.05)' },
              ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } },
            },
            y: {
              grid: { color: 'rgba(255, 255, 255, 0.05)' },
              ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } },
            },
          },
  };

  const getChartIcon = () => {
    if (chartType === 'line') return <TrendingUp className="h-4 w-4 text-cyan-400" />;
    if (chartType === 'doughnut' || chartType === 'pie') return <PieChart className="h-4 w-4 text-purple-400" />;
    return <BarChart3 className="h-4 w-4 text-emerald-400" />;
  };

  return (
    <div className="my-3 rounded-xl border border-white/[0.08] bg-[#090d18] p-4 shadow-lg">
      <div className="flex items-center gap-2 mb-3 border-b border-white/[0.06] pb-2.5">
        {getChartIcon()}
        <span className="font-display text-xs sm:text-sm font-bold text-white uppercase tracking-wide">
          {spec.options?.plugins?.title?.text || `${chartType.toUpperCase()} Analytics Visualization`}
        </span>
      </div>

      <div className="h-64 sm:h-72 w-full">
        {chartType === 'line' && <Line data={enhancedData} options={chartOptions} />}
        {chartType === 'bar' && <Bar data={enhancedData} options={chartOptions} />}
        {chartType === 'doughnut' && <Doughnut data={enhancedData} options={chartOptions} />}
        {chartType === 'pie' && <Pie data={enhancedData} options={chartOptions} />}
      </div>
    </div>
  );
};
