'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { 
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline';
import { kpiApi } from '@/lib/api/kpis';
import { toast } from 'react-hot-toast';

interface KPIFormData {
  name: string;
  description: string;
  category: string;
  unit: string;
  target_value: string;
  current_value: string;
  calculation_method: string;
  frequency: string;
  data_source: string;
  threshold_warning: string;
  threshold_critical: string;
}

const categories = [
  { value: 'financial', label: 'Financial', description: 'Revenue, profit, costs, ROI' },
  { value: 'operational', label: 'Operational', description: 'Efficiency, productivity, quality' },
  { value: 'customer', label: 'Customer', description: 'Satisfaction, retention, acquisition' },
  { value: 'employee', label: 'Employee', description: 'HR metrics, satisfaction, performance' },
  { value: 'marketing', label: 'Marketing', description: 'Campaigns, leads, conversions' },
  { value: 'other', label: 'Other', description: 'Custom or miscellaneous KPIs' }
];

const units = [
  { value: '$', label: 'Currency ($)' },
  { value: '%', label: 'Percentage (%)' },
  { value: '#', label: 'Count (#)' },
  { value: 'hrs', label: 'Hours' },
  { value: 'days', label: 'Days' },
  { value: 'units', label: 'Units' },
  { value: 'score', label: 'Score' },
  { value: 'ratio', label: 'Ratio' },
  { value: 'custom', label: 'Custom Unit' }
];

const frequencies = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'yearly', label: 'Yearly' },
  { value: 'real-time', label: 'Real-time' }
];

export default function EditKPIPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const kpiId = parseInt(params.id as string);

  const [isLoading, setIsLoading] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [formData, setFormData] = useState<KPIFormData>({
    name: '',
    description: '',
    category: '',
    unit: '$',
    target_value: '',
    current_value: '',
    calculation_method: '',
    frequency: 'monthly',
    data_source: '',
    threshold_warning: '',
    threshold_critical: ''
  });

  const { data: kpi, isLoading: kpiLoading, error } = useQuery({
    queryKey: ['kpi', kpiId],
    queryFn: () => kpiApi.getKPI(kpiId),
    enabled: !!kpiId,
  });

  // Populate form when KPI data is loaded
  useEffect(() => {
    if (kpi) {
      setFormData({
        name: kpi.name || '',
        description: kpi.description || '',
        category: kpi.category || '',
        unit: kpi.unit || '$',
        target_value: kpi.target_value ? kpi.target_value.toString() : '',
        current_value: kpi.current_value ? kpi.current_value.toString() : '',
        calculation_method: kpi.calculation_method || '',
        frequency: kpi.frequency || 'monthly',
        data_source: kpi.data_source || '',
        threshold_warning: kpi.threshold_warning ? kpi.threshold_warning.toString() : '',
        threshold_critical: kpi.threshold_critical ? kpi.threshold_critical.toString() : ''
      });
    }
  }, [kpi]);

  const updateFormData = (field: keyof KPIFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear validation error when user starts typing
    if (validationErrors[field]) {
      setValidationErrors(prev => ({ ...prev, [field]: '' }));
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    if (!formData.name.trim()) errors.name = 'KPI name is required';
    if (!formData.description.trim()) errors.description = 'Description is required';
    if (!formData.category) errors.category = 'Category is required';
    if (!formData.unit) errors.unit = 'Unit is required';

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) return;
    
    setIsLoading(true);
    
    try {
      const updateData = {
        name: formData.name,
        description: formData.description,
        category: formData.category,
        unit: formData.unit,
        target_value: formData.target_value ? parseFloat(formData.target_value) : undefined,
        current_value: formData.current_value ? parseFloat(formData.current_value) : undefined,
        calculation_method: formData.calculation_method || undefined,
        frequency: formData.frequency || undefined,
        data_source: formData.data_source || undefined,
        threshold_warning: formData.threshold_warning ? parseFloat(formData.threshold_warning) : undefined,
        threshold_critical: formData.threshold_critical ? parseFloat(formData.threshold_critical) : undefined,
      };

      await kpiApi.updateKPI(kpiId, updateData);
      
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['kpi', kpiId] });
      queryClient.invalidateQueries({ queryKey: ['kpis'] });
      
      toast.success('KPI updated successfully!');
      router.push(`/dashboard/kpis/${kpiId}`);
    } catch (error: any) {
      console.error('Error updating KPI:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to update KPI';
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  if (kpiLoading) {
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
          <p className="mt-1 text-sm text-gray-500">The KPI you're trying to edit doesn't exist or has been deleted.</p>
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
        <div className="flex items-center space-x-4">
          <button
            onClick={() => router.back()}
            className="flex items-center text-gray-600 hover:text-gray-900"
          >
            <ArrowLeftIcon className="h-5 w-5 mr-1" />
            Back
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Edit KPI</h1>
            <p className="text-gray-500">Update "{kpi.name}" details</p>
          </div>
        </div>

        {/* Form */}
        <div className="bg-white shadow rounded-lg">
          <form onSubmit={handleSubmit} className="p-6 space-y-6">
            {/* Basic Information */}
            <div className="border-b border-gray-200 pb-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Basic Information</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    KPI Name *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => updateFormData('name', e.target.value)}
                    className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ${
                      validationErrors.name ? 'border-red-300' : 'border-gray-300'
                    }`}
                    placeholder="Enter KPI name"
                  />
                  {validationErrors.name && (
                    <p className="mt-1 text-sm text-red-600">{validationErrors.name}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Category *
                  </label>
                  <select
                    value={formData.category}
                    onChange={(e) => updateFormData('category', e.target.value)}
                    className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ${
                      validationErrors.category ? 'border-red-300' : 'border-gray-300'
                    }`}
                  >
                    <option value="">Select a category</option>
                    {categories.map((category) => (
                      <option key={category.value} value={category.value}>
                        {category.label}
                      </option>
                    ))}
                  </select>
                  {validationErrors.category && (
                    <p className="mt-1 text-sm text-red-600">{validationErrors.category}</p>
                  )}
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Description *
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => updateFormData('description', e.target.value)}
                    rows={3}
                    className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ${
                      validationErrors.description ? 'border-red-300' : 'border-gray-300'
                    }`}
                    placeholder="Describe what this KPI measures"
                  />
                  {validationErrors.description && (
                    <p className="mt-1 text-sm text-red-600">{validationErrors.description}</p>
                  )}
                </div>
              </div>
            </div>

            {/* Values and Targets */}
            <div className="border-b border-gray-200 pb-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Values and Targets</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Unit *
                  </label>
                  <select
                    value={formData.unit}
                    onChange={(e) => updateFormData('unit', e.target.value)}
                    className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ${
                      validationErrors.unit ? 'border-red-300' : 'border-gray-300'
                    }`}
                  >
                    {units.map((unit) => (
                      <option key={unit.value} value={unit.value}>
                        {unit.label}
                      </option>
                    ))}
                  </select>
                  {validationErrors.unit && (
                    <p className="mt-1 text-sm text-red-600">{validationErrors.unit}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Current Value
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.current_value}
                    onChange={(e) => updateFormData('current_value', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    placeholder="0"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Target Value
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.target_value}
                    onChange={(e) => updateFormData('target_value', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    placeholder="0"
                  />
                </div>
              </div>
            </div>

            {/* Configuration */}
            <div className="border-b border-gray-200 pb-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Configuration</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Frequency
                  </label>
                  <select
                    value={formData.frequency}
                    onChange={(e) => updateFormData('frequency', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  >
                    {frequencies.map((freq) => (
                      <option key={freq.value} value={freq.value}>
                        {freq.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Data Source
                  </label>
                  <input
                    type="text"
                    value={formData.data_source}
                    onChange={(e) => updateFormData('data_source', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    placeholder="e.g., Sales CRM, Google Analytics"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Warning Threshold
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.threshold_warning}
                    onChange={(e) => updateFormData('threshold_warning', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    placeholder="0"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Critical Threshold
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.threshold_critical}
                    onChange={(e) => updateFormData('threshold_critical', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    placeholder="0"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Calculation Method
                  </label>
                  <textarea
                    value={formData.calculation_method}
                    onChange={(e) => updateFormData('calculation_method', e.target.value)}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    placeholder="Describe how this KPI is calculated"
                  />
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end space-x-3">
              <button
                type="button"
                onClick={() => router.back()}
                className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading}
                className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                    </svg>
                    Updating...
                  </>
                ) : (
                  'Update KPI'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </DashboardLayout>
  );
}