'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { KPICard } from '@/components/dashboard/KPICard';
import { ChartWidget } from '@/components/dashboard/ChartWidget';
import { FileUploadWidget } from '@/components/dashboard/FileUploadWidget';
import { AnalyticsWidget } from '@/components/dashboard/AnalyticsWidget';
import { useQuery } from '@tanstack/react-query';
import { kpiApi, analyticsApi } from '@/lib/api';
import { toast } from 'react-hot-toast';

export default function DashboardPage() {
  const { user, token } = useAuth();
  const [organizationId, setOrganizationId] = useState(1); // Default organization

  // Fetch KPIs
  const { data: kpis, isLoading: kpisLoading } = useQuery({
    queryKey: ['kpis', organizationId],
    queryFn: () => kpiApi.getKPIs(organizationId),
    enabled: !!token && !!organizationId,
  });

  // Fetch analytics recommendations
  const { data: recommendations } = useQuery({
    queryKey: ['recommendations', organizationId],
    queryFn: () => analyticsApi.getRecommendations(organizationId),
    enabled: !!token && !!organizationId,
  });

  // Sample chart data
  const chartData = {
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    datasets: [
      {
        label: 'Revenue',
        data: [12000, 19000, 15000, 25000, 22000, 30000],
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
      },
      {
        label: 'Expenses',
        data: [8000, 12000, 10000, 18000, 15000, 22000],
        borderColor: 'rgb(239, 68, 68)',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
      },
    ],
  };

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="loading-spinner loading-spinner-lg" />
      </div>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Welcome Section */}
        <div className="bg-gradient-to-r from-primary-600 to-primary-800 rounded-lg p-6 text-white">
          <h1 className="text-2xl font-bold">
            Welcome back, {user.full_name || user.username}!
          </h1>
          <p className="text-primary-100 mt-2">
            Here's what's happening with your KPIs today.
          </p>
        </div>

        {/* KPI Overview Cards */}
        <div className="dashboard-grid dashboard-grid-4">
          {kpisLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="kpi-card animate-pulse">
                <div className="card-body">
                  <div className="h-4 bg-secondary-200 rounded w-3/4 mb-2"></div>
                  <div className="h-8 bg-secondary-200 rounded w-1/2"></div>
                </div>
              </div>
            ))
          ) : (
            kpis?.slice(0, 4).map((kpi) => (
              <KPICard key={kpi.id} kpi={kpi} />
            ))
          )}
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Chart Widget */}
          <div className="lg:col-span-2">
            <ChartWidget
              title="Revenue vs Expenses"
              data={chartData}
              type="line"
            />
          </div>

          {/* File Upload Widget */}
          <div>
            <FileUploadWidget organizationId={organizationId} />
          </div>
        </div>

        {/* Analytics and Recommendations */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <AnalyticsWidget
            title="AI Insights"
            data={recommendations?.[0] || null}
          />
          
          <div className="card">
            <div className="card-header">
              <h3 className="text-lg font-semibold text-secondary-900">
                Quick Actions
              </h3>
            </div>
            <div className="card-body">
              <div className="space-y-3">
                <button className="btn btn-primary w-full">
                  Create New KPI
                </button>
                <button className="btn btn-outline w-full">
                  Upload Document
                </button>
                <button className="btn btn-outline w-full">
                  Generate Report
                </button>
                <button className="btn btn-outline w-full">
                  Ask AI Question
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-lg font-semibold text-secondary-900">
              Recent Activity
            </h3>
          </div>
          <div className="card-body">
            <div className="space-y-4">
              <div className="flex items-center space-x-3">
                <div className="w-2 h-2 bg-success-500 rounded-full"></div>
                <span className="text-sm text-secondary-600">
                  KPI "Monthly Revenue" updated to $30,000
                </span>
                <span className="text-xs text-secondary-400">2 hours ago</span>
              </div>
              <div className="flex items-center space-x-3">
                <div className="w-2 h-2 bg-primary-500 rounded-full"></div>
                <span className="text-sm text-secondary-600">
                  New document "Q4_Report.pdf" uploaded
                </span>
                <span className="text-xs text-secondary-400">4 hours ago</span>
              </div>
              <div className="flex items-center space-x-3">
                <div className="w-2 h-2 bg-warning-500 rounded-full"></div>
                <span className="text-sm text-secondary-600">
                  KPI "Customer Satisfaction" below target
                </span>
                <span className="text-xs text-secondary-400">1 day ago</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
} 