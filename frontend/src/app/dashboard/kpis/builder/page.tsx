'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { 
  InformationCircleIcon,
  ChartBarIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';
import { useAuth } from '@/components/auth/AuthProvider';
import { toast } from 'react-hot-toast';
import { kpiApi } from '@/lib/api/kpis';
import { useQueryClient } from '@tanstack/react-query';

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
  { value: 'financial', label: 'Financial', icon: '💰', description: 'Revenue, profit, costs, ROI' },
  { value: 'operational', label: 'Operational', icon: '⚙️', description: 'Efficiency, productivity, quality' },
  { value: 'customer', label: 'Customer', icon: '👥', description: 'Satisfaction, retention, acquisition' },
  { value: 'employee', label: 'Employee', icon: '👨‍💼', description: 'HR metrics, satisfaction, performance' },
  { value: 'marketing', label: 'Marketing', icon: '📈', description: 'Campaigns, leads, conversions' },
  { value: 'other', label: 'Other', icon: '📊', description: 'Custom or miscellaneous KPIs' }
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

export default function KPIBuilderPage() {
  const router = useRouter();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [currentStep, setCurrentStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [showSuccess, setShowSuccess] = useState(false);
  const [createdKPIName, setCreatedKPIName] = useState('');
  
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

  const steps = [
    { id: 1, name: 'Basic Info', icon: DocumentTextIcon, description: 'Name and description' },
    { id: 2, name: 'Category & Unit', icon: ChartBarIcon, description: 'Classification and measurement' },
    { id: 3, name: 'Values & Targets', icon: ChartBarIcon, description: 'Current and target values' },
    { id: 4, name: 'Configuration', icon: ChartBarIcon, description: 'Calculation and frequency' },
    { id: 5, name: 'Review', icon: CheckCircleIcon, description: 'Review and submit' }
  ];

  const updateFormData = (field: keyof KPIFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear validation error when user starts typing
    if (validationErrors[field]) {
      setValidationErrors(prev => ({ ...prev, [field]: '' }));
    }
  };

  const resetForm = () => {
    setFormData({
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
    setCurrentStep(1);
    setValidationErrors({});
    setShowSuccess(false);
    setCreatedKPIName('');
  };

  const validateStep = (step: number): boolean => {
    const errors: Record<string, string> = {};

    switch (step) {
      case 1:
        if (!formData.name.trim()) errors.name = 'KPI name is required';
        if (!formData.description.trim()) errors.description = 'Description is required';
        break;
      case 2:
        if (!formData.category || formData.category === '') errors.category = 'Category is required';
        if (!formData.unit) errors.unit = 'Unit is required';
        break;
      case 3:
        if (formData.target_value && isNaN(Number(formData.target_value))) {
          errors.target_value = 'Target value must be a number';
        }
        if (formData.current_value && isNaN(Number(formData.current_value))) {
          errors.current_value = 'Current value must be a number';
        }
        break;
      case 4:
        if (!formData.frequency) errors.frequency = 'Update frequency is required';
        break;
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const nextStep = () => {
    if (validateStep(currentStep)) {
      setCurrentStep(prev => Math.min(prev + 1, steps.length));
    }
  };

  const prevStep = () => {
    setCurrentStep(prev => Math.max(prev - 1, 1));
  };

  const handleSubmit = async () => {
    if (!validateStep(currentStep)) return;
    
    setIsLoading(true);
    
    try {
      const kpiData = {
        name: formData.name,
        description: formData.description,
        category: formData.category || 'other',
        unit: formData.unit === 'custom' ? formData.unit : formData.unit,
        target_value: formData.target_value ? parseFloat(formData.target_value) : undefined,
        current_value: formData.current_value ? parseFloat(formData.current_value) : undefined,
        calculation_method: formData.calculation_method || undefined,
        frequency: formData.frequency || undefined,
        data_source: formData.data_source || undefined,
        threshold_warning: formData.threshold_warning ? parseFloat(formData.threshold_warning) : undefined,
        threshold_critical: formData.threshold_critical ? parseFloat(formData.threshold_critical) : undefined,
        organization_id: user?.organization_id || 1, // Use user's organization or fallback to 1
        is_active: true,
        kpi_metadata: {
          created_via: 'kpi_builder',
          builder_version: '1.0'
        }
      };

      const createdKPI = await kpiApi.createKPI(kpiData);
      
      // Invalidate and refetch KPI queries so the overview page shows the new KPI
      queryClient.invalidateQueries({ queryKey: ['kpis'] });
      
      setCreatedKPIName(formData.name);
      setShowSuccess(true);
      toast.success('KPI created successfully!');
      
    } catch (error: any) {
      console.error('Error creating KPI:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to create KPI';
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 1:
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                KPI Name *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => updateFormData('name', e.target.value)}
                placeholder="e.g., Monthly Revenue Growth"
                className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ${
                  validationErrors.name ? 'border-red-300' : 'border-gray-300'
                }`}
              />
              {validationErrors.name && (
                <p className="mt-1 text-sm text-red-600">{validationErrors.name}</p>
              )}
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Description *
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => updateFormData('description', e.target.value)}
                placeholder="Describe what this KPI measures and why it's important..."
                rows={4}
                className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ${
                  validationErrors.description ? 'border-red-300' : 'border-gray-300'
                }`}
              />
              {validationErrors.description && (
                <p className="mt-1 text-sm text-red-600">{validationErrors.description}</p>
              )}
            </div>

            <div className="bg-blue-50 p-4 rounded-md">
              <div className="flex">
                <InformationCircleIcon className="h-5 w-5 text-blue-400 mt-0.5" />
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-blue-800">
                    Tips for naming KPIs
                  </h3>
                  <div className="mt-2 text-sm text-blue-700">
                    <ul className="list-disc pl-5 space-y-1">
                      <li>Be specific and measurable</li>
                      <li>Include the time period if relevant</li>
                      <li>Use business-friendly language</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );

      case 2:
        return (
          <div className="space-y-6">
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
                    {category.icon} {category.label} - {category.description}
                  </option>
                ))}
              </select>
              {validationErrors.category && (
                <p className="mt-1 text-sm text-red-600">{validationErrors.category}</p>
              )}
            </div>

            {/* Category Info Card */}
            {formData.category && (
              <div className="bg-blue-50 border border-blue-200 rounded-md p-4">
                <div className="flex items-start">
                  <div className="text-2xl mr-3">
                    {categories.find(c => c.value === formData.category)?.icon}
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-blue-800">
                      {categories.find(c => c.value === formData.category)?.label} KPIs
                    </h3>
                    <p className="mt-1 text-sm text-blue-700">
                      {categories.find(c => c.value === formData.category)?.description}
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Unit of Measurement *
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
          </div>
        );

      case 3:
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Current Value
              </label>
              <div className="relative">
                <input
                  type="number"
                  step="0.01"
                  value={formData.current_value}
                  onChange={(e) => updateFormData('current_value', e.target.value)}
                  placeholder="0.00"
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ${
                    validationErrors.current_value ? 'border-red-300' : 'border-gray-300'
                  }`}
                />
                <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                  <span className="text-gray-500 text-sm">{formData.unit}</span>
                </div>
              </div>
              {validationErrors.current_value && (
                <p className="mt-1 text-sm text-red-600">{validationErrors.current_value}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Target Value
              </label>
              <div className="relative">
                <input
                  type="number"
                  step="0.01"
                  value={formData.target_value}
                  onChange={(e) => updateFormData('target_value', e.target.value)}
                  placeholder="0.00"
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 ${
                    validationErrors.target_value ? 'border-red-300' : 'border-gray-300'
                  }`}
                />
                <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                  <span className="text-gray-500 text-sm">{formData.unit}</span>
                </div>
              </div>
              {validationErrors.target_value && (
                <p className="mt-1 text-sm text-red-600">{validationErrors.target_value}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Warning Threshold
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.01"
                    value={formData.threshold_warning}
                    onChange={(e) => updateFormData('threshold_warning', e.target.value)}
                    placeholder="0.00"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  />
                  <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                    <span className="text-gray-500 text-sm">{formData.unit}</span>
                  </div>
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Critical Threshold
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.01"
                    value={formData.threshold_critical}
                    onChange={(e) => updateFormData('threshold_critical', e.target.value)}
                    placeholder="0.00"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  />
                  <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                    <span className="text-gray-500 text-sm">{formData.unit}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );

      case 4:
        return (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Update Frequency *
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
                Calculation Method
              </label>
              <textarea
                value={formData.calculation_method}
                onChange={(e) => updateFormData('calculation_method', e.target.value)}
                placeholder="Describe how this KPI is calculated (e.g., Total Revenue / Number of Customers)"
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Data Source
              </label>
              <input
                type="text"
                value={formData.data_source}
                onChange={(e) => updateFormData('data_source', e.target.value)}
                placeholder="e.g., CRM System, Financial Database, Analytics Platform"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
          </div>
        );

      case 5:
        return (
          <div className="space-y-6">
            <div className="bg-green-50 border border-green-200 rounded-md p-4">
              <div className="flex">
                <CheckCircleIcon className="h-5 w-5 text-green-400 mt-0.5" />
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-green-800">
                    Ready to Create KPI
                  </h3>
                  <p className="mt-1 text-sm text-green-700">
                    Review the information below and click "Create KPI" to save.
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">KPI Summary</h3>
              
              <dl className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
                <div>
                  <dt className="text-sm font-medium text-gray-500">Name</dt>
                  <dd className="mt-1 text-sm text-gray-900">{formData.name}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500">Category</dt>
                  <dd className="mt-1 text-sm text-gray-900">
                    {formData.category ? categories.find(c => c.value === formData.category)?.label : 'Not selected'}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500">Unit</dt>
                  <dd className="mt-1 text-sm text-gray-900">{formData.unit}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500">Frequency</dt>
                  <dd className="mt-1 text-sm text-gray-900 capitalize">{formData.frequency}</dd>
                </div>
                {formData.current_value && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500">Current Value</dt>
                    <dd className="mt-1 text-sm text-gray-900">{formData.current_value} {formData.unit}</dd>
                  </div>
                )}
                {formData.target_value && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500">Target Value</dt>
                    <dd className="mt-1 text-sm text-gray-900">{formData.target_value} {formData.unit}</dd>
                  </div>
                )}
                <div className="sm:col-span-2">
                  <dt className="text-sm font-medium text-gray-500">Description</dt>
                  <dd className="mt-1 text-sm text-gray-900">{formData.description}</dd>
                </div>
              </dl>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  // Success State Component
  const SuccessState = () => (
    <div className="text-center py-12">
      <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100">
        <CheckCircleIcon className="h-6 w-6 text-green-600" />
      </div>
      <h2 className="mt-4 text-lg font-semibold text-gray-900">KPI Created Successfully!</h2>
      <p className="mt-2 text-sm text-gray-500">
        "{createdKPIName}" has been created and saved to your organization.
      </p>
      <div className="mt-8 flex justify-center space-x-4">
        <button
          onClick={resetForm}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
        >
          Create Another KPI
        </button>
        <button
          onClick={() => router.push('/dashboard/kpis')}
          className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
        >
          View All KPIs
        </button>
      </div>
    </div>
  );

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900">KPI Builder</h1>
          <p className="text-gray-500 mt-2">Create a new Key Performance Indicator</p>
        </div>

        {/* Show success state or form */}
        {showSuccess ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
            <SuccessState />
          </div>
        ) : (
          <>
            {/* Progress Steps */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <nav aria-label="Progress">
                <ol className="flex items-center">
                  {steps.map((step, stepIdx) => {
                    const StepIcon = step.icon;
                    const isCurrentStep = step.id === currentStep;
                    const isCompletedStep = step.id < currentStep;
                    
                    return (
                      <li key={step.id} className={stepIdx !== steps.length - 1 ? 'pr-8 sm:pr-20' : ''}>
                        <div className="relative flex items-center">
                          <div
                            className={`relative flex h-8 w-8 items-center justify-center rounded-full ${
                              isCurrentStep
                                ? 'bg-primary-600 text-white'
                                : isCompletedStep
                                ? 'bg-green-500 text-white'
                                : 'bg-gray-300 text-gray-500'
                            }`}
                          >
                            {isCompletedStep ? (
                              <CheckCircleIcon className="h-5 w-5" />
                            ) : (
                              <StepIcon className="h-5 w-5" />
                            )}
                          </div>
                          <div className="ml-4 min-w-0 flex-1">
                            <p className={`text-sm font-medium ${
                              isCurrentStep ? 'text-primary-600' : isCompletedStep ? 'text-green-600' : 'text-gray-500'
                            }`}>
                              {step.name}
                            </p>
                            <p className="text-xs text-gray-500">{step.description}</p>
                          </div>
                          {stepIdx !== steps.length - 1 && (
                            <div className="absolute top-4 left-8 -ml-px h-0.5 w-full bg-gray-300" />
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </nav>
            </div>

            {/* Form Content */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="space-y-6">
                {renderStepContent()}
              </div>
            </div>

            {/* Navigation Buttons */}
            <div className="flex justify-between">
              {currentStep > 1 && (
                <button
                  type="button"
                  onClick={() => setCurrentStep(currentStep - 1)}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                >
                  Previous
                </button>
              )}
              
              <div className="ml-auto">
                {currentStep < steps.length ? (
                  <button
                    type="button"
                    onClick={() => {
                      if (validateStep(currentStep)) {
                        setCurrentStep(currentStep + 1);
                      }
                    }}
                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                  >
                    Next
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleSubmit}
                    disabled={isLoading}
                    className="inline-flex items-center px-6 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isLoading ? (
                      <>
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                        </svg>
                        Creating KPI...
                      </>
                    ) : (
                      'Create KPI'
                    )}
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}