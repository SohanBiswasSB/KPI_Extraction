'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useAuth } from './AuthProvider';
import { toast } from 'react-hot-toast';
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline';

const registerSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  username: z.string().min(3, 'Username must be at least 3 characters').max(50, 'Username must be less than 50 characters'),
  full_name: z.string().min(2, 'Full name must be at least 2 characters').optional(),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  confirmPassword: z.string(),
}).refine((data) => data.password === data.confirmPassword, {
  message: "Passwords don't match",
  path: ["confirmPassword"],
});

type RegisterFormData = z.infer<typeof registerSchema>;

interface RegisterFormProps {
  onSuccess?: () => void;
}

export function RegisterForm({ onSuccess }: RegisterFormProps) {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const { register: registerUser } = useAuth();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data: RegisterFormData) => {
    setIsLoading(true);
    try {
      await registerUser({
        email: data.email,
        username: data.username,
        password: data.password,
        full_name: data.full_name,
      });
      toast.success('Account created successfully! Please sign in.');
      onSuccess?.();
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Registration failed. Please try again.';
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-secondary-700">
            Email Address
          </label>
          <div className="mt-1">
            <input
              {...register('email')}
              type="email"
              id="email"
              className="input"
              placeholder="Enter your email"
              disabled={isLoading}
            />
            {errors.email && (
              <p className="mt-1 text-sm text-danger-600">{errors.email.message}</p>
            )}
          </div>
        </div>

        <div>
          <label htmlFor="username" className="block text-sm font-medium text-secondary-700">
            Username
          </label>
          <div className="mt-1">
            <input
              {...register('username')}
              type="text"
              id="username"
              className="input"
              placeholder="Choose a username"
              disabled={isLoading}
            />
            {errors.username && (
              <p className="mt-1 text-sm text-danger-600">{errors.username.message}</p>
            )}
          </div>
        </div>
      </div>

      <div>
        <label htmlFor="full_name" className="block text-sm font-medium text-secondary-700">
          Full Name (Optional)
        </label>
        <div className="mt-1">
          <input
            {...register('full_name')}
            type="text"
            id="full_name"
            className="input"
            placeholder="Enter your full name"
            disabled={isLoading}
          />
          {errors.full_name && (
            <p className="mt-1 text-sm text-danger-600">{errors.full_name.message}</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <label htmlFor="password" className="block text-sm font-medium text-secondary-700">
            Password
          </label>
          <div className="mt-1 relative">
            <input
              {...register('password')}
              type={showPassword ? 'text' : 'password'}
              id="password"
              className="input pr-10"
              placeholder="Create a password"
              disabled={isLoading}
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 pr-3 flex items-center"
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? (
                <EyeSlashIcon className="h-5 w-5 text-secondary-400" />
              ) : (
                <EyeIcon className="h-5 w-5 text-secondary-400" />
              )}
            </button>
            {errors.password && (
              <p className="mt-1 text-sm text-danger-600">{errors.password.message}</p>
            )}
          </div>
        </div>

        <div>
          <label htmlFor="confirmPassword" className="block text-sm font-medium text-secondary-700">
            Confirm Password
          </label>
          <div className="mt-1 relative">
            <input
              {...register('confirmPassword')}
              type={showConfirmPassword ? 'text' : 'password'}
              id="confirmPassword"
              className="input pr-10"
              placeholder="Confirm your password"
              disabled={isLoading}
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 pr-3 flex items-center"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
            >
              {showConfirmPassword ? (
                <EyeSlashIcon className="h-5 w-5 text-secondary-400" />
              ) : (
                <EyeIcon className="h-5 w-5 text-secondary-400" />
              )}
            </button>
            {errors.confirmPassword && (
              <p className="mt-1 text-sm text-danger-600">{errors.confirmPassword.message}</p>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-start">
        <div className="flex items-center h-5">
          <input
            id="terms"
            name="terms"
            type="checkbox"
            required
            className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-secondary-300 rounded"
          />
        </div>
        <div className="ml-3 text-sm">
          <label htmlFor="terms" className="text-secondary-700">
            I agree to the{' '}
            <a href="#" className="font-medium text-primary-600 hover:text-primary-500">
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="#" className="font-medium text-primary-600 hover:text-primary-500">
              Privacy Policy
            </a>
          </label>
        </div>
      </div>

      <div>
        <button
          type="submit"
          disabled={isLoading}
          className="btn btn-primary w-full btn-lg"
        >
          {isLoading ? (
            <div className="flex items-center">
              <div className="loading-spinner loading-spinner-sm mr-2" />
              Creating account...
            </div>
          ) : (
            'Create Account'
          )}
        </button>
      </div>


    </form>
  );
} 