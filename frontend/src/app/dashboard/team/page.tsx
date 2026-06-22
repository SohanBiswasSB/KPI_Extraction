'use client';

import { useState } from 'react';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { 
  PlusIcon,
  MagnifyingGlassIcon,
  UserGroupIcon,
  EnvelopeIcon,
  PhoneIcon,
  EllipsisHorizontalIcon,
  PencilIcon,
  TrashIcon,
  UserIcon
} from '@heroicons/react/24/outline';
import { Menu } from '@headlessui/react';

interface TeamMember {
  id: number;
  name: string;
  email: string;
  role: string;
  department: string;
  status: 'active' | 'pending' | 'inactive';
  avatar?: string;
  joinedDate: string;
  lastActive: string;
  kpisManaged: number;
}

const mockTeamMembers: TeamMember[] = [
  {
    id: 1,
    name: 'Sarah Johnson',
    email: 'sarah.johnson@company.com',
    role: 'admin',
    department: 'Leadership',
    status: 'active',
    joinedDate: '2023-01-15',
    lastActive: '2 hours ago',
    kpisManaged: 12
  },
  {
    id: 2,
    name: 'Michael Chen',
    email: 'michael.chen@company.com',
    role: 'manager',
    department: 'Sales',
    status: 'active',
    joinedDate: '2023-03-22',
    lastActive: '1 day ago',
    kpisManaged: 8
  },
  {
    id: 3,
    name: 'Emily Rodriguez',
    email: 'emily.rodriguez@company.com',
    role: 'analyst',
    department: 'Marketing',
    status: 'active',
    joinedDate: '2023-06-10',
    lastActive: '5 minutes ago',
    kpisManaged: 15
  },
  {
    id: 4,
    name: 'David Kim',
    email: 'david.kim@company.com',
    role: 'viewer',
    department: 'Operations',
    status: 'pending',
    joinedDate: '2024-01-28',
    lastActive: 'Never',
    kpisManaged: 0
  },
  {
    id: 5,
    name: 'Lisa Thompson',
    email: 'lisa.thompson@company.com',
    role: 'analyst',
    department: 'Finance',
    status: 'inactive',
    joinedDate: '2022-11-05',
    lastActive: '2 weeks ago',
    kpisManaged: 6
  }
];

const roleColors = {
  admin: 'bg-purple-100 text-purple-800',
  manager: 'bg-blue-100 text-blue-800',
  analyst: 'bg-green-100 text-green-800',
  viewer: 'bg-gray-100 text-gray-800'
};

const statusColors = {
  active: 'bg-green-100 text-green-800',
  pending: 'bg-yellow-100 text-yellow-800',
  inactive: 'bg-red-100 text-red-800'
};

const departments = ['All Departments', 'Leadership', 'Sales', 'Marketing', 'Operations', 'Finance', 'HR', 'IT'];
const roles = ['All Roles', 'admin', 'manager', 'analyst', 'viewer'];

export default function TeamPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDepartment, setSelectedDepartment] = useState('All Departments');
  const [selectedRole, setSelectedRole] = useState('All Roles');
  const [selectedStatus, setSelectedStatus] = useState('All Status');

  const filteredMembers = mockTeamMembers.filter(member => {
    const matchesSearch = member.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         member.email.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesDepartment = selectedDepartment === 'All Departments' || member.department === selectedDepartment;
    const matchesRole = selectedRole === 'All Roles' || member.role === selectedRole;
    const matchesStatus = selectedStatus === 'All Status' || member.status === selectedStatus;
    
    return matchesSearch && matchesDepartment && matchesRole && matchesStatus;
  });

  const getInitials = (name: string) => {
    return name.split(' ').map(n => n[0]).join('').toUpperCase();
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="md:flex md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:truncate sm:text-3xl sm:tracking-tight">
              Team Management
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Manage team members, roles, and permissions
            </p>
          </div>
          <div className="mt-4 flex gap-3 md:ml-4 md:mt-0">
            <button
              type="button"
              className="inline-flex items-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
            >
              <EnvelopeIcon className="-ml-0.5 mr-1.5 h-5 w-5 text-gray-400" />
              Invite Team
            </button>
            <button
              type="button"
              className="inline-flex items-center rounded-md bg-primary-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
            >
              <PlusIcon className="-ml-0.5 mr-1.5 h-5 w-5" />
              Add Member
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <UserGroupIcon className="h-6 w-6 text-gray-400" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Total Members
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">{mockTeamMembers.length}</dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="h-6 w-6 rounded-full bg-green-100 flex items-center justify-center">
                    <div className="h-3 w-3 rounded-full bg-green-500"></div>
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Active Members
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {mockTeamMembers.filter(m => m.status === 'active').length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="h-6 w-6 rounded-full bg-yellow-100 flex items-center justify-center">
                    <div className="h-3 w-3 rounded-full bg-yellow-500"></div>
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Pending Invites
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {mockTeamMembers.filter(m => m.status === 'pending').length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="h-6 w-6 rounded-full bg-blue-100 flex items-center justify-center">
                    <div className="h-3 w-3 rounded-full bg-blue-500"></div>
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Departments
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {departments.length - 1}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <MagnifyingGlassIcon className="pointer-events-none absolute inset-y-0 left-0 h-full w-5 text-gray-400 pl-3" />
            <input
              type="text"
              placeholder="Search team members..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="block w-full rounded-md border-0 py-1.5 pl-10 pr-3 text-gray-900 ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6"
            />
          </div>

          {/* Department Filter */}
          <select
            value={selectedDepartment}
            onChange={(e) => setSelectedDepartment(e.target.value)}
            className="rounded-md border-0 py-1.5 pl-3 pr-8 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-primary-600 sm:text-sm"
          >
            {departments.map((dept) => (
              <option key={dept} value={dept}>{dept}</option>
            ))}
          </select>

          {/* Role Filter */}
          <select
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
            className="rounded-md border-0 py-1.5 pl-3 pr-8 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-primary-600 sm:text-sm"
          >
            {roles.map((role) => (
              <option key={role} value={role}>{role}</option>
            ))}
          </select>

          {/* Status Filter */}
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="rounded-md border-0 py-1.5 pl-3 pr-8 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-primary-600 sm:text-sm"
          >
            <option value="All Status">All Status</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>

        {/* Team Members Grid */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filteredMembers.map((member) => (
            <div key={member.id} className="bg-white overflow-hidden shadow rounded-lg hover:shadow-md transition-shadow">
              <div className="px-4 py-5 sm:p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="h-12 w-12 rounded-full bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-white font-semibold">
                      {getInitials(member.name)}
                    </div>
                    <div className="ml-4">
                      <h3 className="text-lg font-medium text-gray-900">{member.name}</h3>
                      <p className="text-sm text-gray-500">{member.department}</p>
                    </div>
                  </div>
                  
                  <Menu as="div" className="relative">
                    <Menu.Button className="p-1 rounded-full hover:bg-gray-100">
                      <EllipsisHorizontalIcon className="h-5 w-5 text-gray-400" />
                    </Menu.Button>
                    <Menu.Items className="absolute right-0 z-10 mt-2 w-32 origin-top-right rounded-md bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
                      <Menu.Item>
                        {({ active }) => (
                          <button className={`${active ? 'bg-gray-50' : ''} flex items-center px-4 py-2 text-sm text-gray-700 w-full`}>
                            <UserIcon className="mr-2 h-4 w-4" />
                            View Profile
                          </button>
                        )}
                      </Menu.Item>
                      <Menu.Item>
                        {({ active }) => (
                          <button className={`${active ? 'bg-gray-50' : ''} flex items-center px-4 py-2 text-sm text-gray-700 w-full`}>
                            <PencilIcon className="mr-2 h-4 w-4" />
                            Edit
                          </button>
                        )}
                      </Menu.Item>
                      <Menu.Item>
                        {({ active }) => (
                          <button className={`${active ? 'bg-gray-50' : ''} flex items-center px-4 py-2 text-sm text-red-700 w-full`}>
                            <TrashIcon className="mr-2 h-4 w-4" />
                            Remove
                          </button>
                        )}
                      </Menu.Item>
                    </Menu.Items>
                  </Menu>
                </div>

                <div className="mt-4 space-y-2">
                  <div className="flex items-center text-sm text-gray-500">
                    <EnvelopeIcon className="h-4 w-4 mr-2" />
                    {member.email}
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${roleColors[member.role]}`}>
                      {member.role.charAt(0).toUpperCase() + member.role.slice(1)}
                    </span>
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${statusColors[member.status]}`}>
                      {member.status.charAt(0).toUpperCase() + member.status.slice(1)}
                    </span>
                  </div>

                  <div className="flex justify-between text-xs text-gray-500 pt-2 border-t">
                    <span>{member.kpisManaged} KPIs managed</span>
                    <span>Last active: {member.lastActive}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Empty State */}
        {filteredMembers.length === 0 && (
          <div className="text-center py-12">
            <UserGroupIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-semibold text-gray-900">No team members found</h3>
            <p className="mt-1 text-sm text-gray-500">
              {searchQuery ? 'Try adjusting your search terms.' : 'Get started by adding your first team member.'}
            </p>
            <div className="mt-6">
              <button
                type="button"
                className="inline-flex items-center rounded-md bg-primary-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-500"
              >
                <PlusIcon className="-ml-0.5 mr-1.5 h-5 w-5" />
                Add Member
              </button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}