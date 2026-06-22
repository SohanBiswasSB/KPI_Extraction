'use client';

import { Fragment, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { 
  UserCircleIcon,
  ArrowRightOnRectangleIcon,
  CogIcon,
  UserIcon,
  ChevronUpIcon,
  ChevronDownIcon
} from '@heroicons/react/24/outline';
import { Menu, Transition } from '@headlessui/react';
import Link from 'next/link';

export function UserProfile({ isCollapsed = false }: { isCollapsed?: boolean }) {
  const { user, logout } = useAuth();
  const [isExpanded, setIsExpanded] = useState(false);

  if (!user) return null;

  const userInitials = user.full_name 
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase()
    : user.username.substring(0, 2).toUpperCase();

  return (
    <div className="border-t border-gray-200 bg-gray-50">
      {/* User Profile Section */}
      <div className={isCollapsed ? "p-2" : "p-4"}>
        {isCollapsed ? (
          // Collapsed view - show only avatar
          <div className="flex justify-center">
            <div 
              className="h-10 w-10 rounded-full bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-white font-semibold text-sm cursor-pointer hover:scale-105 transition-transform"
              title={user.full_name || user.username}
            >
              {userInitials}
            </div>
          </div>
        ) : (
          // Expanded view
          <>
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex w-full items-center space-x-3 rounded-lg p-2 text-left text-sm font-medium text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-colors"
            >
              {/* Avatar */}
              <div className="flex-shrink-0">
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-white font-semibold text-sm">
                  {userInitials}
                </div>
              </div>
              
              {/* User Info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {user.full_name || user.username}
                </p>
                <p className="text-xs text-gray-500 truncate">
                  {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                </p>
              </div>
              
              {/* Expand Icon */}
              <div className="flex-shrink-0">
                {isExpanded ? (
                  <ChevronUpIcon className="h-4 w-4 text-gray-400" />
                ) : (
                  <ChevronDownIcon className="h-4 w-4 text-gray-400" />
                )}
              </div>
            </button>

            {/* Expanded User Menu */}
            {isExpanded && (
              <div className="mt-3 space-y-1">
                <Link
                  href="/dashboard/profile"
                  className="flex items-center space-x-3 rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  <UserIcon className="h-4 w-4 text-gray-500" />
                  <span>View Profile</span>
                </Link>
                
                <Link
                  href="/dashboard/settings"
                  className="flex items-center space-x-3 rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  <CogIcon className="h-4 w-4 text-gray-500" />
                  <span>Settings</span>
                </Link>
                
                <hr className="my-2 border-gray-200" />
                
                <button
                  onClick={logout}
                  className="flex w-full items-center space-x-3 rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-red-50 hover:text-red-700 transition-colors"
                >
                  <ArrowRightOnRectangleIcon className="h-4 w-4" />
                  <span>Sign out</span>
                </button>
              </div>
            )}

            {/* Quick Stats */}
            <div className="border-t border-gray-200 mt-4 pt-4">
              <div className="grid grid-cols-2 gap-4 text-center">
                <div>
                  <p className="text-lg font-semibold text-gray-900">12</p>
                  <p className="text-xs text-gray-500">Active KPIs</p>
                </div>
                <div>
                  <p className="text-lg font-semibold text-gray-900">8</p>
                  <p className="text-xs text-gray-500">Reports</p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}