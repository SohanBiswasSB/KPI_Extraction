'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { 
  ArrowLeftIcon,
  PencilIcon,
  TrashIcon,
  ChartBarIcon,
  TrendingUpIcon,
  TrendingDownIcon,
  ClockIcon,
  TagIcon,
  CurrencyDollarIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline';
import { kpiApi } from '@/lib/api/kpis';
import { toast } from 'react-hot-toast';

export default function KPIDetailPage() {
  const params = useParams();
  const router = useRouter();
  const kpiId = parseInt(params.id as string);

  const { data: kpi, isLoading, error } = useQuery({
    queryKey: ['kpi', kpiId],
    queryFn: () => kpiApi.getKPI(kpiId),
    enabled: !!kpiId,
  });

  const handleEdit = () => {
    router.push(`/dashboard/kpis/${kpiId}/edit`);
  };

  const handleDelete = async () => {
    if (confirm('Are you sure you want to delete this KPI? This action cannot be undone.')) {
      try {
        await kpiApi.deleteKPI(kpiId);
        toast.success('KPI deleted successfully');
        router.push('/dashboard/kpis');
      } catch (error) {
        toast.error('Failed to delete KPI');
      }
    }
  };

  const getStatusColor = (kpi: any) => {
    if (!kpi.current_value || !kpi.target_value) return 'text-gray-500';
    const ratio = kpi.current_value / kpi.target_value;
    if (ratio >= 1.0) return 'text-green-600';
    if (ratio >= 0.8) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getStatusIcon = (kpi: any) => {
    if (!kpi.current_value || !kpi.target_value) return null;
    const ratio = kpi.current_value / kpi.target_value;
    if (ratio >= 1.0) return <CheckCircleIcon className="h-5 w-5 text-green-600" />;
    if (ratio >= 0.8) return <ExclamationTriangleIcon className="h-5 w-5 text-yellow-600" />;
    return <ExclamationTriangleIcon className="h-5 w-5 text-red-600" />;
  };

  const getTrendIcon = (kpi: any) => {
    if (!kpi.current_value || !kpi.target_value) return null;
    const ratio = kpi.current_value / kpi.target_value;
    return ratio >= 1.0 ? 
      <TrendingUpIcon className="h-5 w-5 text-green-600" /> : 
      <TrendingDownIcon className="h-5 w-5 text-red-600" />;
  };

  if (isLoading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        </div>
      </DashboardLayout>
    );
  }

  if (error || !kpi) {
    return (
      <DashboardLayout>
        <div className="text-center py-12">
          <div className="mx-auto h-12 w-12 text-red-400">
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="mt-2 text-lg font-semibold text-gray-900">KPI Not Found</h3>
          <p className="mt-1 text-sm text-gray-500">The KPI you're looking for doesn't exist or has been deleted.</p>
          <div className="mt-6">
            <button
              onClick={() => router.push('/dashboard/kpis')}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
            >
              Back to KPIs
            </button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => router.back()}
              className="flex items-center text-gray-600 hover:text-gray-900"
            >
              <ArrowLeftIcon className="h-5 w-5 mr-1" />
              Back
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{kpi.name}</h1>
              <p className="text-gray-500">KPI Details</p>
            </div>
          </div>
          <div className="flex space-x-2">
            <button
              onClick={handleEdit}
              className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              <PencilIcon className="h-4 w-4 mr-1" />
              Edit
            </button>
            <button
              onClick={handleDelete}
              className="inline-flex items-center px-3 py-2 border border-transparent shadow-sm text-sm leading-4 font-medium rounded-md text-white bg-red-600 hover:bg-red-700"
            >
              <TrashIcon className="h-4 w-4 mr-1" />
              Delete
            </button>
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* KPI Overview Card */}
          <div className="lg:col-span-2">
            <div className="bg-white shadow rounded-lg p-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-medium text-gray-900">KPI Overview</h2>
                <div className="flex items-center space-x-2">
                  {getStatusIcon(kpi)}
                  {getTrendIcon(kpi)}
                </div>
              </div>

              {/* Current vs Target */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div className="text-center">
                  <div className="text-3xl font-bold text-gray-900">
                    {kpi.current_value ? `${kpi.current_value}${kpi.unit || ''}` : 'No data'}
                  </div>
                  <div className="text-sm text-gray-500">Current Value</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-gray-600">
                    {kpi.target_value ? `${kpi.target_value}${kpi.unit || ''}` : 'No target'}
                  </div>
                  <div className="text-sm text-gray-500">Target Value</div>
                </div>
              </div>

              {/* Progress Bar */}
              {kpi.current_value && kpi.target_value && (
                <div className="mb-6">
                  <div className="flex justify-between text-sm text-gray-600 mb-1">
                    <span>Progress to Target</span>
                    <span>{Math.round((kpi.current_value / kpi.target_value) * 100)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className={`h-2 rounded-full ${
                        kpi.current_value >= kpi.target_value ? 'bg-green-600' : 
                        kpi.current_value >= kpi.target_value * 0.8 ? 'bg-yellow-600' : 'bg-red-600'
                      }`}
                      style={{ width: `${Math.min((kpi.current_value / kpi.target_value) * 100, 100)}%` }}
                    ></div>
                  </div>
                </div>
              )}

              {/* Description */}
              {kpi.description && (
                <div className="border-t pt-6">
                  <h3 className="text-sm font-medium text-gray-900 mb-2">Description</h3>
                  <p className="text-sm text-gray-600">{kpi.description}</p>
                </div>
              )}
            </div>
          </div>

          {/* Details Sidebar */}
          <div className="space-y-6">
            {/* Basic Details */}
            <div className="bg-white shadow rounded-lg p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Details</h3>
              <dl className="space-y-4">
                <div>
                  <dt className="text-sm font-medium text-gray-500 flex items-center">
                    <TagIcon className="h-4 w-4 mr-1" />
                    Category
                  </dt>
                  <dd className="mt-1 text-sm text-gray-900 capitalize">{kpi.category}</dd>
                </div>
                {kpi.unit && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500 flex items-center">
                      <CurrencyDollarIcon className="h-4 w-4 mr-1" />
                      Unit
                    </dt>
                    <dd className="mt-1 text-sm text-gray-900">{kpi.unit}</dd>
                  </div>
                )}
                {kpi.frequency && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500 flex items-center">
                      <ClockIcon className="h-4 w-4 mr-1" />
                      Frequency
                    </dt>
                    <dd className="mt-1 text-sm text-gray-900 capitalize">{kpi.frequency}</dd>
                  </div>
                )}
                {kpi.data_source && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500 flex items-center">
                      <ChartBarIcon className="h-4 w-4 mr-1" />
                      Data Source
                    </dt>
                    <dd className="mt-1 text-sm text-gray-900">{kpi.data_source}</dd>
                  </div>
                )}
              </dl>
            </div>

            {/* Thresholds */}
            {(kpi.threshold_warning || kpi.threshold_critical) && (
              <div className="bg-white shadow rounded-lg p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Thresholds</h3>
                <dl className="space-y-4">
                  {kpi.threshold_warning && (
                    <div>
                      <dt className="text-sm font-medium text-yellow-600">Warning Threshold</dt>
                      <dd className="mt-1 text-sm text-gray-900">{kpi.threshold_warning}{kpi.unit || ''}</dd>
                    </div>
                  )}
                  {kpi.threshold_critical && (
                    <div>
                      <dt className="text-sm font-medium text-red-600">Critical Threshold</dt>
                      <dd className="mt-1 text-sm text-gray-900">{kpi.threshold_critical}{kpi.unit || ''}</dd>
                    </div>
                  )}
                </dl>
              </div>
            )}

            {/* Calculation Method */}
            {kpi.calculation_method && (
              <div className="bg-white shadow rounded-lg p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Calculation</h3>
                <p className="text-sm text-gray-600">{kpi.calculation_method}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}