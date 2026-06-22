'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { SparklesIcon } from '@heroicons/react/24/outline';
import { LoginForm } from '@/components/auth/LoginForm';
import { RegisterForm } from '@/components/auth/RegisterForm';

export default function HomePage() {
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const router = useRouter();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-white to-secondary-50">
      <div className="w-full max-w-md px-6">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center space-x-2 mb-4">
            <SparklesIcon className="h-8 w-8 text-primary-600" />
            <span className="text-xl font-bold gradient-text">
              KPI Extraction Platform
            </span>
          </div>
        </div>

        {/* Auth Card */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-2xl font-bold text-secondary-900 text-center">
              {authMode === 'login' ? 'Sign In to Your Account' : 'Create Your Account'}
            </h2>
            <p className="mt-2 text-sm text-secondary-600 text-center">
              {authMode === 'login' 
                ? 'Access your KPI dashboards and analytics' 
                : 'Start your journey with AI-powered KPI analytics'
              }
            </p>
          </div>
          <div className="card-body">
            {authMode === 'login' ? (
              <LoginForm onSuccess={() => router.push('/dashboard')} />
            ) : (
              <RegisterForm onSuccess={() => router.push('/dashboard')} />
            )}
            <div className="mt-6 text-center">
              <button
                onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
                className="text-sm text-primary-600 hover:text-primary-500"
              >
                {authMode === 'login' 
                  ? "Don't have an account? Sign up here" 
                  : "Already have an account? Sign in here"
                }
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
} 