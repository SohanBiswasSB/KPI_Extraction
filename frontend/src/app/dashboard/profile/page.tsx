'use client';

import { useState } from 'react';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { useAuth } from '@/components/auth/AuthProvider';
import { 
  UserIcon,
  EnvelopeIcon,
  PhoneIcon,
  BuildingOfficeIcon,
  CalendarIcon,
  CogIcon,
  KeyIcon,
  BellIcon,
  EyeIcon,
  PencilIcon
} from '@heroicons/react/24/outline';

export default function ProfilePage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('profile');
  const [isEditing, setIsEditing] = useState(false);

  if (!user) return null;

  const userInitials = user.full_name 
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase()
    : user.username.substring(0, 2).toUpperCase();

  const tabs = [
    { id: 'profile', name: 'Profile', icon: UserIcon },
    { id: 'security', name: 'Security', icon: KeyIcon },
    { id: 'notifications', name: 'Notifications', icon: BellIcon },
    { id: 'preferences', name: 'Preferences', icon: CogIcon }
  ];

  const ProfileTab = () => (
    <div className="space-y-6">
      {/* Profile Header */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-8">
          <div className="flex items-center space-x-6">
            <div className="h-24 w-24 rounded-full bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-white font-bold text-2xl">
              {userInitials}
            </div>
            <div className="flex-1">
              <h3 className="text-2xl font-bold text-gray-900">{user.full_name || user.username}</h3>
              <p className="text-gray-500">{user.email}</p>
              <p className="text-sm text-gray-400 capitalize">
                {user.role} • Member since January 2024
              </p>
            </div>
            <button
              onClick={() => setIsEditing(!isEditing)}
              className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
            >
              {isEditing ? (
                <>
                  <EyeIcon className="h-4 w-4 mr-2" />
                  View Profile
                </>
              ) : (
                <>
                  <PencilIcon className="h-4 w-4 mr-2" />
                  Edit Profile
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Profile Information */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Personal Information</h3>
        </div>
        <div className="px-6 py-4">
          {isEditing ? (
            <form className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Full Name</label>
                  <input
                    type="text"
                    defaultValue={user.full_name || ''}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Username</label>
                  <input
                    type="text"
                    defaultValue={user.username}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Email</label>
                  <input
                    type="email"
                    defaultValue={user.email}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Phone</label>
                  <input
                    type="tel"
                    placeholder="+1 (555) 123-4567"
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Job Title</label>
                  <input
                    type="text"
                    placeholder="e.g. Senior Data Analyst"
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Department</label>
                  <select className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500">
                    <option>Analytics</option>
                    <option>Sales</option>
                    <option>Marketing</option>
                    <option>Operations</option>
                    <option>Finance</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-primary-600 border border-transparent rounded-md text-sm font-medium text-white hover:bg-primary-700"
                >
                  Save Changes
                </button>
              </div>
            </form>
          ) : (
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-6">
              <div>
                <dt className="text-sm font-medium text-gray-500 flex items-center">
                  <UserIcon className="h-4 w-4 mr-2" />
                  Full Name
                </dt>
                <dd className="mt-1 text-sm text-gray-900">{user.full_name || 'Not specified'}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 flex items-center">
                  <EnvelopeIcon className="h-4 w-4 mr-2" />
                  Email
                </dt>
                <dd className="mt-1 text-sm text-gray-900">{user.email}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 flex items-center">
                  <PhoneIcon className="h-4 w-4 mr-2" />
                  Phone
                </dt>
                <dd className="mt-1 text-sm text-gray-900">Not specified</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 flex items-center">
                  <BuildingOfficeIcon className="h-4 w-4 mr-2" />
                  Department
                </dt>
                <dd className="mt-1 text-sm text-gray-900">Analytics</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 flex items-center">
                  <CalendarIcon className="h-4 w-4 mr-2" />
                  Member Since
                </dt>
                <dd className="mt-1 text-sm text-gray-900">January 15, 2024</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Role</dt>
                <dd className="mt-1">
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-primary-100 text-primary-800 capitalize">
                    {user.role}
                  </span>
                </dd>
              </div>
            </dl>
          )}
        </div>
      </div>

      {/* Activity Stats */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Activity Overview</h3>
        </div>
        <div className="px-6 py-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center">
              <div className="text-2xl font-bold text-primary-600">12</div>
              <div className="text-sm text-gray-500">KPIs Created</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">45</div>
              <div className="text-sm text-gray-500">Reports Generated</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">23</div>
              <div className="text-sm text-gray-500">Files Uploaded</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const SecurityTab = () => (
    <div className="space-y-6">
      {/* Change Password */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Change Password</h3>
        </div>
        <div className="px-6 py-4">
          <form className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Current Password</label>
              <input
                type="password"
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">New Password</label>
              <input
                type="password"
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Confirm New Password</label>
              <input
                type="password"
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
              />
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                className="px-4 py-2 bg-primary-600 border border-transparent rounded-md text-sm font-medium text-white hover:bg-primary-700"
              >
                Update Password
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Two-Factor Authentication */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Two-Factor Authentication</h3>
        </div>
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-900">Secure your account with 2FA</p>
              <p className="text-sm text-gray-500">Add an extra layer of security to your account</p>
            </div>
            <button className="px-4 py-2 bg-green-600 border border-transparent rounded-md text-sm font-medium text-white hover:bg-green-700">
              Enable 2FA
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'profile':
        return <ProfileTab />;
      case 'security':
        return <SecurityTab />;
      case 'notifications':
        return <div className="bg-white shadow rounded-lg p-6">Notifications settings coming soon...</div>;
      case 'preferences':
        return <div className="bg-white shadow rounded-lg p-6">Preferences settings coming soon...</div>;
      default:
        return <ProfileTab />;
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:truncate sm:text-3xl sm:tracking-tight">
            User Profile
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Manage your account settings and preferences
          </p>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex space-x-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center py-2 px-1 border-b-2 font-medium text-sm ${
                    activeTab === tab.id
                      ? 'border-primary-500 text-primary-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {tab.name}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Tab Content */}
        {renderTabContent()}
      </div>
    </DashboardLayout>
  );
}