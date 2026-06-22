'use client';

import { useState } from 'react';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { ChartWidget } from '@/components/dashboard/ChartWidget';
import { AnalyticsWidget } from '@/components/dashboard/AnalyticsWidget';
import { 
  CalendarIcon,
  ArrowDownTrayIcon,
  ChartBarIcon,
  PresentationChartLineIcon,
  DocumentChartBarIcon
} from '@heroicons/react/24/outline';

const timeRanges = [
  { label: 'Last 7 days', value: '7d' },
  { label: 'Last 30 days', value: '30d' },
  { label: 'Last 3 months', value: '3m' },
  { label: 'Last 6 months', value: '6m' },
  { label: 'Last year', value: '1y' }
];

const mockChartData = {
  performance: {
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    datasets: [
      {
        label: 'Revenue',
        data: [12000, 19000, 15000, 25000, 22000, 30000],
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
      },
      {
        label: 'Target',
        data: [15000, 20000, 18000, 24000, 25000, 28000],
        borderColor: 'rgb(34, 197, 94)',
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
      }
    ]
  },
  trends: {
    labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
    datasets: [
      {
        label: 'Customer Satisfaction',
        data: [4.2, 4.5, 4.3, 4.7],
        borderColor: 'rgb(168, 85, 247)',
        backgroundColor: 'rgba(168, 85, 247, 0.1)',
      }
    ]
  },
  distribution: {
    labels: ['Q1', 'Q2', 'Q3', 'Q4'],
    datasets: [
      {
        label: 'Quarterly Performance',
        data: [65, 78, 82, 88],
        backgroundColor: [
          'rgba(239, 68, 68, 0.8)',
          'rgba(245, 158, 11, 0.8)',
          'rgba(34, 197, 94, 0.8)',
          'rgba(59, 130, 246, 0.8)'
        ]
      }
    ]
  }
};

const mockRecommendations = [
  {
    title: 'Revenue Growth Opportunity',
    description: 'Customer satisfaction scores show strong correlation with revenue growth. Focus on improving service quality.',
    impact: 'High',
    type: 'insight'
  },
  {
    title: 'Performance Alert',
    description: 'Q3 performance metrics indicate a potential bottleneck in the sales process.',
    impact: 'Medium',
    type: 'warning'
  },
  {
    title: 'Optimization Suggestion',
    description: 'Consider reallocating resources to high-performing segments for better ROI.',
    impact: 'Medium',
    type: 'suggestion'
  }
];

export default function AnalyticsPage() {
  const [selectedTimeRange, setSelectedTimeRange] = useState('30d');

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="md:flex md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:truncate sm:text-3xl sm:tracking-tight">
              Analytics Dashboard
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Advanced insights and performance analytics for your KPIs
            </p>
          </div>
          <div className="mt-4 flex gap-3 md:ml-4 md:mt-0">
            <select
              value={selectedTimeRange}
              onChange={(e) => setSelectedTimeRange(e.target.value)}
              className="rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-primary-600 sm:text-sm sm:leading-6"
            >
              {timeRanges.map((range) => (
                <option key={range.value} value={range.value}>
                  {range.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="inline-flex items-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
            >
              <ArrowDownTrayIcon className="-ml-0.5 mr-1.5 h-5 w-5 text-gray-400" />
              Export
            </button>
          </div>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <ChartBarIcon className="h-6 w-6 text-gray-400" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Total KPIs
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">24</dd>
                  </dl>
                </div>
              </div>
            </div>
            <div className="bg-gray-50 px-5 py-3">
              <div className="text-sm">
                <span className="font-medium text-green-600">+12%</span>
                <span className="text-gray-500"> from last month</span>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <PresentationChartLineIcon className="h-6 w-6 text-gray-400" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Avg Performance
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">87.3%</dd>
                  </dl>
                </div>
              </div>
            </div>
            <div className="bg-gray-50 px-5 py-3">
              <div className="text-sm">
                <span className="font-medium text-green-600">+5.2%</span>
                <span className="text-gray-500"> from last month</span>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <DocumentChartBarIcon className="h-6 w-6 text-gray-400" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Reports Generated
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">156</dd>
                  </dl>
                </div>
              </div>
            </div>
            <div className="bg-gray-50 px-5 py-3">
              <div className="text-sm">
                <span className="font-medium text-green-600">+23%</span>
                <span className="text-gray-500"> from last month</span>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <CalendarIcon className="h-6 w-6 text-gray-400" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Data Freshness
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">2 mins</dd>
                  </dl>
                </div>
              </div>
            </div>
            <div className="bg-gray-50 px-5 py-3">
              <div className="text-sm">
                <span className="text-green-600 font-medium">Real-time</span>
                <span className="text-gray-500"> updates</span>
              </div>
            </div>
          </div>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ChartWidget
            title="Performance vs Targets"
            data={mockChartData.performance}
            type="line"
          />
          <ChartWidget
            title="Trend Analysis"
            data={mockChartData.trends}
            type="line"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <ChartWidget
              title="Quarterly Distribution"
              data={mockChartData.distribution}
              type="doughnut"
            />
          </div>
          <div className="lg:col-span-2 space-y-6">
            <h3 className="text-lg font-medium text-gray-900">AI Insights & Recommendations</h3>
            {mockRecommendations.map((recommendation, index) => (
              <AnalyticsWidget
                key={index}
                title={recommendation.title}
                data={recommendation}
              />
            ))}
          </div>
        </div>

        {/* Advanced Analytics */}
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Advanced Analytics
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <div className="text-2xl font-bold text-primary-600">94.7%</div>
                <div className="text-sm text-gray-500">Accuracy Score</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">+15.3%</div>
                <div className="text-sm text-gray-500">Growth Rate</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600">67</div>
                <div className="text-sm text-gray-500">Predictive Score</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}