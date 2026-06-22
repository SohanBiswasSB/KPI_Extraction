'use client';

import { 
  LightBulbIcon, 
  ArrowTrendingUpIcon, 
  ExclamationTriangleIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline';

interface AnalyticsWidgetProps {
  title: string;
  data: any;
}

export function AnalyticsWidget({ title, data }: AnalyticsWidgetProps) {
  if (!data) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="text-lg font-semibold text-secondary-900">{title}</h3>
        </div>
        <div className="card-body">
          <div className="flex items-center justify-center h-32 text-secondary-500">
            <div className="text-center">
              <LightBulbIcon className="h-8 w-8 mx-auto mb-2" />
              <p className="text-sm">No insights available yet</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const getHealthScoreColor = (score: number) => {
    if (score >= 80) return 'text-success-600';
    if (score >= 60) return 'text-warning-600';
    return 'text-danger-600';
  };

  const getHealthScoreIcon = (score: number) => {
    if (score >= 80) return <CheckCircleIcon className="h-5 w-5" />;
    if (score >= 60) return <ExclamationTriangleIcon className="h-5 w-5" />;
    return <ExclamationTriangleIcon className="h-5 w-5" />;
  };

  return (
    <div className="card">
      <div className="card-header">
        <div className="flex items-center space-x-2">
          <LightBulbIcon className="h-5 w-5 text-primary-600" />
          <h3 className="text-lg font-semibold text-secondary-900">{title}</h3>
        </div>
      </div>
      <div className="card-body">
        {/* Health Score */}
        {data.overall_score && (
          <div className="mb-4 p-3 bg-secondary-50 rounded-lg">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-secondary-700">Overall Health Score</span>
              <div className={`flex items-center space-x-1 ${getHealthScoreColor(data.overall_score)}`}>
                {getHealthScoreIcon(data.overall_score)}
                <span className="font-bold">{data.overall_score}/100</span>
              </div>
            </div>
          </div>
        )}

        {/* Health Assessment */}
        {data.health_assessment && (
          <div className="mb-4">
            <h4 className="text-sm font-medium text-secondary-900 mb-2">Assessment</h4>
            <p className="text-sm text-secondary-600">{data.health_assessment}</p>
          </div>
        )}

        {/* Priority Areas */}
        {data.priority_areas && data.priority_areas.length > 0 && (
          <div className="mb-4">
            <h4 className="text-sm font-medium text-secondary-900 mb-2">Priority Areas</h4>
            <ul className="space-y-1">
              {data.priority_areas.map((area: string, index: number) => (
                <li key={index} className="flex items-start space-x-2">
                  <ArrowTrendingUpIcon className="h-4 w-4 text-warning-500 mt-0.5 flex-shrink-0" />
                  <span className="text-sm text-secondary-600">{area}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Strategic Recommendations */}
        {data.strategic_recommendations && data.strategic_recommendations.length > 0 && (
          <div className="mb-4">
            <h4 className="text-sm font-medium text-secondary-900 mb-2">Recommendations</h4>
            <ul className="space-y-2">
              {data.strategic_recommendations.map((rec: string, index: number) => (
                <li key={index} className="flex items-start space-x-2">
                  <div className="w-2 h-2 bg-primary-500 rounded-full mt-2 flex-shrink-0"></div>
                  <span className="text-sm text-secondary-600">{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Missing Categories */}
        {data.missing_categories && data.missing_categories.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-secondary-900 mb-2">Missing KPI Categories</h4>
            <div className="flex flex-wrap gap-2">
              {data.missing_categories.map((category: string, index: number) => (
                <span
                  key={index}
                  className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-warning-100 text-warning-800"
                >
                  {category}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Action Button */}
        <div className="mt-4 pt-4 border-t border-secondary-200">
          <button className="btn btn-primary w-full btn-sm">
            View Detailed Analysis
          </button>
        </div>
      </div>
    </div>
  );
} 