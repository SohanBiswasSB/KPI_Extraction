'use client';

import { useState } from 'react';
import { DashboardLayout } from '@/components/dashboard/DashboardLayout';
import { TableViewer } from '@/components/dashboard/TableViewer';
import { 
  CloudArrowUpIcon,
  MagnifyingGlassIcon,
  FolderIcon,
  DocumentTextIcon,
  DocumentIcon,
  EyeIcon,
  ArrowDownTrayIcon,
  TrashIcon,
  PlusIcon,
  FunnelIcon
} from '@heroicons/react/24/outline';
import { Menu } from '@headlessui/react';

interface FileItem {
  id: number;
  name: string;
  type: 'folder' | 'pdf' | 'excel' | 'csv' | 'doc';
  size?: string;
  modified: string;
  status: 'processing' | 'completed' | 'failed' | 'uploaded';
  extractedKPIs?: number;
}

const mockFiles: FileItem[] = [
  {
    id: 1,
    name: 'Q4 Financial Reports',
    type: 'folder',
    modified: '2 hours ago',
    status: 'completed'
  },
  {
    id: 2,
    name: 'Revenue_Analysis_2024.pdf',
    type: 'pdf',
    size: '2.4 MB',
    modified: '1 day ago',
    status: 'completed',
    extractedKPIs: 8
  },
  {
    id: 3,
    name: 'Sales_Data.xlsx',
    type: 'excel',
    size: '1.2 MB',
    modified: '3 days ago',
    status: 'processing',
    extractedKPIs: 0
  },
  {
    id: 4,
    name: 'Customer_Metrics.csv',
    type: 'csv',
    size: '856 KB',
    modified: '1 week ago',
    status: 'completed',
    extractedKPIs: 12
  },
  {
    id: 5,
    name: 'Marketing_Report.docx',
    type: 'doc',
    size: '3.1 MB',
    modified: '2 weeks ago',
    status: 'failed',
    extractedKPIs: 0
  }
];

const fileTypeIcons = {
  folder: FolderIcon,
  pdf: DocumentTextIcon,
  excel: DocumentIcon,
  csv: DocumentIcon,
  doc: DocumentTextIcon
};

const statusColors = {
  processing: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  uploaded: 'bg-blue-100 text-blue-800'
};

export default function FilesPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [tablesFor, setTablesFor] = useState<FileItem | null>(null);

  const filteredFiles = mockFiles.filter(file => {
    const matchesSearch = file.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = selectedType === 'all' || file.type === selectedType;
    const matchesStatus = selectedStatus === 'all' || file.status === selectedStatus;
    return matchesSearch && matchesType && matchesStatus;
  });

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="md:flex md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:truncate sm:text-3xl sm:tracking-tight">
              File Manager
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Upload, manage, and analyze your documents and data files
            </p>
          </div>
          <div className="mt-4 flex gap-3 md:ml-4 md:mt-0">
            <button
              type="button"
              className="inline-flex items-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
            >
              <FolderIcon className="-ml-0.5 mr-1.5 h-5 w-5 text-gray-400" />
              New Folder
            </button>
            <button
              type="button"
              className="inline-flex items-center rounded-md bg-primary-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
            >
              <CloudArrowUpIcon className="-ml-0.5 mr-1.5 h-5 w-5" />
              Upload Files
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
              placeholder="Search files..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="block w-full rounded-md border-0 py-1.5 pl-10 pr-3 text-gray-900 ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6"
            />
          </div>

          {/* Filters */}
          <div className="flex gap-2">
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="rounded-md border-0 py-1.5 pl-3 pr-8 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-primary-600 sm:text-sm"
            >
              <option value="all">All Types</option>
              <option value="folder">Folders</option>
              <option value="pdf">PDF</option>
              <option value="excel">Excel</option>
              <option value="csv">CSV</option>
              <option value="doc">Documents</option>
            </select>

            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="rounded-md border-0 py-1.5 pl-3 pr-8 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-primary-600 sm:text-sm"
            >
              <option value="all">All Status</option>
              <option value="completed">Completed</option>
              <option value="processing">Processing</option>
              <option value="failed">Failed</option>
              <option value="uploaded">Uploaded</option>
            </select>

            {/* View Toggle */}
            <div className="flex border border-gray-300 rounded-md">
              <button
                onClick={() => setViewMode('grid')}
                className={`px-3 py-1.5 text-sm font-medium rounded-l-md ${
                  viewMode === 'grid'
                    ? 'bg-primary-50 text-primary-700 border-primary-200'
                    : 'bg-white text-gray-700 hover:bg-gray-50'
                }`}
              >
                Grid
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`px-3 py-1.5 text-sm font-medium rounded-r-md border-l ${
                  viewMode === 'list'
                    ? 'bg-primary-50 text-primary-700 border-primary-200'
                    : 'bg-white text-gray-700 hover:bg-gray-50'
                }`}
              >
                List
              </button>
            </div>
          </div>
        </div>

        {/* File Grid/List */}
        {viewMode === 'grid' ? (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredFiles.map((file) => {
              const IconComponent = fileTypeIcons[file.type];
              return (
                <div
                  key={file.id}
                  className="group relative bg-white p-6 rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow"
                >
                  {/* File Icon and Status */}
                  <div className="flex items-start justify-between">
                    <div className="flex items-center">
                      <IconComponent className="h-8 w-8 text-gray-400" />
                      <span className={`ml-2 inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${statusColors[file.status]}`}>
                        {file.status}
                      </span>
                    </div>
                    
                    {/* Actions */}
                    <Menu as="div" className="relative opacity-0 group-hover:opacity-100 transition-opacity">
                      <Menu.Button className="p-1 rounded hover:bg-gray-100">
                        <svg className="h-5 w-5 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                        </svg>
                      </Menu.Button>
                      <Menu.Items className="absolute right-0 z-10 mt-2 w-32 origin-top-right rounded-md bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
                        <Menu.Item>
                          {({ active }) => (
                            <button className={`${active ? 'bg-gray-50' : ''} flex items-center px-4 py-2 text-sm text-gray-700 w-full`}>
                              <EyeIcon className="mr-2 h-4 w-4" />
                              View
                            </button>
                          )}
                        </Menu.Item>
                        <Menu.Item>
                          {({ active }) => (
                            <button className={`${active ? 'bg-gray-50' : ''} flex items-center px-4 py-2 text-sm text-gray-700 w-full`}>
                              <ArrowDownTrayIcon className="mr-2 h-4 w-4" />
                              Download
                            </button>
                          )}
                        </Menu.Item>
                        <Menu.Item>
                          {({ active }) => (
                            <button className={`${active ? 'bg-gray-50' : ''} flex items-center px-4 py-2 text-sm text-red-700 w-full`}>
                              <TrashIcon className="mr-2 h-4 w-4" />
                              Delete
                            </button>
                          )}
                        </Menu.Item>
                      </Menu.Items>
                    </Menu>
                  </div>

                  {/* File Info */}
                  <div className="mt-4">
                    <h3 className="text-sm font-medium text-gray-900 truncate" title={file.name}>
                      {file.name}
                    </h3>
                    <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
                      <span>{file.size}</span>
                      <span>{file.modified}</span>
                    </div>
                    {file.extractedKPIs !== undefined && file.extractedKPIs > 0 && (
                      <div className="mt-2 text-xs text-primary-600">
                        {file.extractedKPIs} KPIs extracted
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="bg-white shadow overflow-hidden sm:rounded-md">
            <ul className="divide-y divide-gray-200">
              {filteredFiles.map((file) => {
                const IconComponent = fileTypeIcons[file.type];
                return (
                  <li key={file.id} className="px-6 py-4 hover:bg-gray-50">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <IconComponent className="h-6 w-6 text-gray-400" />
                        <div className="ml-4">
                          <p className="text-sm font-medium text-gray-900">{file.name}</p>
                          <div className="flex items-center mt-1 text-xs text-gray-500">
                            <span>{file.size}</span>
                            <span className="mx-2">•</span>
                            <span>{file.modified}</span>
                            {file.extractedKPIs !== undefined && file.extractedKPIs > 0 && (
                              <>
                                <span className="mx-2">•</span>
                                <span className="text-primary-600">{file.extractedKPIs} KPIs</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${statusColors[file.status]}`}>
                          {file.status}
                        </span>
                        <div className="flex space-x-1">
                          <button
                            className="p-1 rounded hover:bg-gray-100"
                            title="View extracted tables"
                            onClick={() => setTablesFor(file)}
                          >
                            <EyeIcon className="h-4 w-4 text-gray-500" />
                          </button>
                          <button className="p-1 rounded hover:bg-gray-100">
                            <ArrowDownTrayIcon className="h-4 w-4 text-gray-500" />
                          </button>
                          <button className="p-1 rounded hover:bg-gray-100">
                            <TrashIcon className="h-4 w-4 text-red-500" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Empty State */}
        {filteredFiles.length === 0 && (
          <div className="text-center py-12">
            <CloudArrowUpIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-semibold text-gray-900">No files found</h3>
            <p className="mt-1 text-sm text-gray-500">
              {searchQuery ? 'Try adjusting your search terms.' : 'Get started by uploading your first file.'}
            </p>
            <div className="mt-6">
              <button
                type="button"
                className="inline-flex items-center rounded-md bg-primary-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-500"
              >
                <CloudArrowUpIcon className="-ml-0.5 mr-1.5 h-5 w-5" />
                Upload Files
              </button>
            </div>
          </div>
        )}

        {/* Extracted-tables modal */}
        {tablesFor && (
          <div
            className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 overflow-y-auto"
            onClick={() => setTablesFor(null)}
          >
            <div className="w-full max-w-5xl mt-10" onClick={(e) => e.stopPropagation()}>
              <TableViewer
                fileId={tablesFor.id}
                filename={tablesFor.name}
                onClose={() => setTablesFor(null)}
              />
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}