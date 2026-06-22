'use client';

import { useState } from 'react';
import { KPI } from '@/lib/api';
import { 
  ArrowUpIcon, 
  ArrowDownIcon, 
  MinusIcon,
  ChartBarIcon,
  EyeIcon
} from '@heroicons/react/24/outline';
import { motion } from 'framer-motion';

interface KPICardProps {
  kpi: KPI;
  onClick?: () => void;
}

export function KPICard({ kpi, onClick }: KPICardProps) {
  const [isHovered, setIsHovered] = useState(false);

  // Calculate trend (mock data for now)
  const getTrend = () => {
    if (!kpi.current_value || !kpi.target_value) return 'neutral';
    const percentage = ((kpi.current_value - kpi.target_value) / kpi.target_value) * 100;
    if (percentage > 5) return 'positive';
    if (percentage < -5) return 'negative';
    return 'neutral';
  };

  const getStatusColor = () => {
    const trend = getTrend();
    switch (trend) {
      case 'positive':
        return 'text-success-600';
      case 'negative':
        return 'text-danger-600';
      default:
        return 'text-secondary-600';
    }
  };

  const getStatusIcon = () => {
    const trend = getTrend();
    switch (trend) {
      case 'positive':
        return <ArrowUpIcon className="h-4 w-4" />;
      case 'negative':
        return <ArrowDownIcon className="h-4 w-4" />;
      default:
        return <MinusIcon className="h-4 w-4" />;
    }
  };

  const formatValue = (value: number | undefined) => {
    if (!value) return 'N/A';
    
    // Format based on value size
    if (value >= 1000000) {
      return `$${(value / 1000000).toFixed(1)}M`;
    } else if (value >= 1000) {
      return `$${(value / 1000).toFixed(1)}K`;
    } else {
      return `$${value.toLocaleString()}`;
    }
  };

  const getCategoryColor = (category: string) => {
    const colors = {
      financial: 'bg-blue-100 text-blue-800',
      operational: 'bg-green-100 text-green-800',
      customer: 'bg-purple-100 text-purple-800',
      employee: 'bg-orange-100 text-orange-800',
      marketing: 'bg-pink-100 text-pink-800',
      other: 'bg-gray-100 text-gray-800',
    };
    return colors[category as keyof typeof colors] || colors.other;
  };

  return (
    <motion.div
      className="kpi-card"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2 }}
    >
      <div className="card-body">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <ChartBarIcon className="h-5 w-5 text-primary-600" />
            <span className={`badge ${getCategoryColor(kpi.category)}`}>
              {kpi.category}
            </span>
          </div>
          {onClick && (
            <button className="text-secondary-400 hover:text-secondary-600">
              <EyeIcon className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="mb-2">
          <h3 className="text-sm font-medium text-secondary-600 truncate">
            {kpi.name}
          </h3>
        </div>

        <div className="flex items-end justify-between">
          <div>
            <div className="kpi-value">
              {formatValue(kpi.current_value)}
            </div>
            {kpi.unit && (
              <div className="text-sm text-secondary-500">
                {kpi.unit}
              </div>
            )}
          </div>

          <div className={`flex items-center space-x-1 ${getStatusColor()}`}>
            {getStatusIcon()}
            <span className="text-sm font-medium">
              {getTrend() === 'positive' ? '+12%' : getTrend() === 'negative' ? '-8%' : '0%'}
            </span>
          </div>
        </div>

        {kpi.target_value && (
          <div className="mt-3 pt-3 border-t border-secondary-100">
            <div className="flex justify-between text-sm">
              <span className="text-secondary-500">Target:</span>
              <span className="font-medium">{formatValue(kpi.target_value)}</span>
            </div>
            
            {/* Progress bar */}
            <div className="mt-2 w-full bg-secondary-200 rounded-full h-2">
              <div 
                className={`h-2 rounded-full transition-all duration-300 ${
                  getTrend() === 'positive' 
                    ? 'bg-success-500' 
                    : getTrend() === 'negative' 
                    ? 'bg-danger-500' 
                    : 'bg-secondary-400'
                }`}
                style={{ 
                  width: `${Math.min(100, Math.max(0, (kpi.current_value || 0) / (kpi.target_value || 1) * 100))}%` 
                }}
              />
            </div>
          </div>
        )}

        {kpi.description && (
          <div className="mt-3 pt-3 border-t border-secondary-100">
            <p className="text-xs text-secondary-600 line-clamp-2">
              {kpi.description}
            </p>
          </div>
        )}

        {/* Hover overlay */}
        {isHovered && onClick && (
          <motion.div
            className="absolute inset-0 bg-primary-600 bg-opacity-10 rounded-lg flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <span className="text-primary-700 font-medium">View Details</span>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
} 