'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { KPICard } from '@/components/dashboard/KPICard';
import { 
  PlusIcon,
  MagnifyingGlassIcon,
  FunnelIcon,
  ArrowDownIcon,
  EyeIcon,
  PencilIcon,
  TrashIcon
} from '@heroicons/react/24/outline';
import { Menu } from '@headlessui/react';
import { useAuth } from '@/components/auth/AuthProvider';
import { kpiApi, KPI } from '@/lib/api/kpis';
import { toast } from 'react-hot-toast';

const categories = ['All', 'Financial', 'Customer', 'Marketing', 'Operational', 'Employee', 'Other'];

// Helper function to get KPI status based on target achievement
const getKPIStatus = (kpi: KPI): 'success' | 'warning' | 'danger' | 'neutral' => {
  if (!kpi.current_value || !kpi.target_value) return 'neutral';
  
  const ratio = kpi.current_value / kpi.target_value;
  
  if (ratio >= 1.0) return 'success';
  if (ratio >= 0.8) return 'warning';
  return 'danger';
};

// Helper function to calculate trend (simplified for display)
const getKPITrend = (kpi: KPI): number => {
  // This would normally come from historical data
  // For now, we'll calculate based on target achievement
  if (!kpi.current_value || !kpi.target_value) return 0;
  
  const ratio = kpi.current_value / kpi.target_value;
  return (ratio - 1) * 100; // Percentage above/below target
};

export default function KPIsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('name');

  // Fetch KPIs from API
  const { data: kpis = [], isLoading, error, refetch } = useQuery({
    queryKey: ['kpis', user?.organization_id, selectedCategory],
    queryFn: async () => {
      if (!user?.organization_id) return [];
      
      const filters: any = {};
      if (selectedCategory !== 'All') {
        filters.category = selectedCategory.toLowerCase();
      }
      
      return await kpiApi.getKPIs(user.organization_id, filters);
    },
    enabled: !!user?.organization_id,
  });

  // Transform KPIs for display (adding status and trend)
  const transformedKPIs = kpis.map(kpi => ({
    ...kpi,
    value: kpi.current_value || 0,
    target: kpi.target_value || 0,
    status: getKPIStatus(kpi),
    trend: getKPITrend(kpi)
  }));

  // Filter KPIs based on search
  const filteredKPIs = transformedKPIs.filter(kpi => {
    const matchesSearch = kpi.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         kpi.description?.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSearch;
  });

  // Sort KPIs
  const sortedKPIs = [...filteredKPIs].sort((a, b) => {
    switch (sortBy) {
      case 'value':
        return (b.current_value || 0) - (a.current_value || 0);
      case 'trend':
        return b.trend - a.trend;
      case 'name':
      default:
        return a.name.localeCompare(b.name);
    }
  });

  const handleCreateKPI = () => {
    router.push('/dashboard/kpis/builder');
  };

  const handleViewKPI = (kpiId: number) => {
    router.push(`/dashboard/kpis/${kpiId}`);
  };

  const handleEditKPI = (kpiId: number) => {
    router.push(`/dashboard/kpis/${kpiId}/edit`);
  };

  const handleDeleteKPI = async (kpiId: number) => {
    if (confirm('Are you sure you want to delete this KPI? This action cannot be undone.')) {
      try {
        await kpiApi.deleteKPI(kpiId);
        toast.success('KPI deleted successfully');
        refetch();
      } catch (error) {
        toast.error('Failed to delete KPI');
      }
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="md:flex md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:truncate sm:text-3xl sm:tracking-tight">
              KPI Management
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Monitor and manage your key performance indicators
            </p>
          </div>
          <div className="mt-4 flex md:ml-4 md:mt-0">
            <button
              type="button"
              onClick={handleCreateKPI}
              className="inline-flex items-center rounded-md bg-primary-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
            >
              <PlusIcon className="-ml-0.5 mr-1.5 h-5 w-5" />
              Create KPI
            </button>
          </div>
        </div>

        {/* Filters and Search */}
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <MagnifyingGlassIcon className="pointer-events-none absolute inset-y-0 left-0 h-full w-5 text-gray-400 pl-3" />
            <input
              type="text"
              placeholder="Search KPIs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="block w-full rounded-md border-0 py-1.5 pl-10 pr-3 text-gray-900 ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6"
            />
          </div>

          {/* Category Filter */}
          <div className="flex gap-2">
            {categories.map((category) => (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  selectedCategory === category
                    ? 'bg-primary-100 text-primary-700 border border-primary-200'
                    : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
                }`}
              >
                {category}
              </button>
            ))}
          </div>

          {/* Sort */}
          <Menu as="div" className="relative">
            <Menu.Button className="inline-flex items-center gap-x-1.5 rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50">
              <FunnelIcon className="-ml-0.5 h-5 w-5 text-gray-400" />
              Sort
              <ArrowDownIcon className="-mr-1 h-5 w-5 text-gray-400" />
            </Menu.Button>
            <Menu.Items className="absolute right-0 z-10 mt-2 w-48 origin-top-right rounded-md bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
              <Menu.Item>
                {({ active }) => (
                  <button
                    className={`${active ? 'bg-gray-50' : ''} block px-4 py-2 text-sm text-gray-700 w-full text-left`}
                    onClick={() => setSortBy('name')}
                  >
                    Name
                  </button>
                )}
              </Menu.Item>
              <Menu.Item>
                {({ active }) => (
                  <button
                    className={`${active ? 'bg-gray-50' : ''} block px-4 py-2 text-sm text-gray-700 w-full text-left`}
                    onClick={() => setSortBy('value')}
                  >
                    Value
                  </button>
                )}
              </Menu.Item>
              <Menu.Item>
                {({ active }) => (
                  <button
                    className={`${active ? 'bg-gray-50' : ''} block px-4 py-2 text-sm text-gray-700 w-full text-left`}
                    onClick={() => setSortBy('trend')}
                  >
                    Trend
                  </button>
                )}
              </Menu.Item>
            </Menu.Items>
          </Menu>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            <p className="mt-2 text-sm text-gray-500">Loading KPIs...</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="text-center py-12">
            <div className="mx-auto h-12 w-12 text-red-400">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="mt-2 text-sm font-semibold text-gray-900">Error loading KPIs</h3>
            <p className="mt-1 text-sm text-gray-500">Please try again later.</p>
            <div className="mt-6">
              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center rounded-md bg-primary-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-500"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {/* KPI Grid */}
        {!isLoading && !error && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {sortedKPIs.map((kpi) => (
              <div key={kpi.id} className="relative group">
                <KPICard kpi={kpi} />
                
                {/* Actions overlay */}
                <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="flex gap-1">
                    <button 
                      className="p-1 rounded bg-white shadow-sm hover:bg-gray-50"
                      title="View Details"
                      onClick={() => handleViewKPI(kpi.id)}
                    >
                      <EyeIcon className="h-4 w-4 text-gray-600" />
                    </button>
                    <button 
                      className="p-1 rounded bg-white shadow-sm hover:bg-gray-50"
                      title="Edit KPI"
                      onClick={() => handleEditKPI(kpi.id)}
                    >
                      <PencilIcon className="h-4 w-4 text-gray-600" />
                    </button>
                    <button 
                      className="p-1 rounded bg-white shadow-sm hover:bg-gray-50"
                      title="Delete KPI"
                      onClick={() => handleDeleteKPI(kpi.id)}
                    >
                      <TrashIcon className="h-4 w-4 text-red-600" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && sortedKPIs.length === 0 && (
          <div className="text-center py-12">
            <div className="mx-auto h-12 w-12 text-gray-400">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="mt-2 text-sm font-semibold text-gray-900">No KPIs found</h3>
            <p className="mt-1 text-sm text-gray-500">
              {searchQuery ? 'Try adjusting your search terms.' : 'Get started by creating your first KPI.'}
            </p>
            <div className="mt-6">
              <button
                type="button"
                onClick={handleCreateKPI}
                className="inline-flex items-center rounded-md bg-primary-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-500"
              >
                <PlusIcon className="-ml-0.5 mr-1.5 h-5 w-5" />
                Create KPI
              </button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}