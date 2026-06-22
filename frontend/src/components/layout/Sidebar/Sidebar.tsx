'use client';

import { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { XMarkIcon, SparklesIcon } from '@heroicons/react/24/outline';
import { SidebarNavigation } from './SidebarNavigation';
import { UserProfile } from './UserProfile';

interface SidebarProps {
  open: boolean;
  setOpen: (open: boolean) => void;
}

function SidebarContent({ onNavigate, isCollapsed, onToggleCollapse }: { 
  onNavigate?: () => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex h-16 shrink-0 items-center border-b border-gray-200 px-4">
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center space-x-2">
            <SparklesIcon className="h-8 w-8 text-primary-600 flex-shrink-0" />
            {!isCollapsed && (
              <div>
                <h1 className="text-lg font-bold text-gray-900">KPI Platform</h1>
                <p className="text-xs text-gray-500">Analytics Dashboard</p>
              </div>
            )}
          </div>
          <button
            onClick={onToggleCollapse}
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? (
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            ) : (
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto">
        <SidebarNavigation onNavigate={onNavigate} isCollapsed={isCollapsed} />
      </div>

      {/* User Profile */}
      <UserProfile isCollapsed={isCollapsed} />
    </div>
  );
}

// Mobile sidebar
export function MobileSidebar({ open, setOpen }: SidebarProps) {
  return (
    <Transition.Root show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50 lg:hidden" onClose={setOpen}>
        <Transition.Child
          as={Fragment}
          enter="transition-opacity ease-linear duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="transition-opacity ease-linear duration-300"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-gray-900/80" />
        </Transition.Child>

        <div className="fixed inset-0 flex">
          <Transition.Child
            as={Fragment}
            enter="transition ease-in-out duration-300 transform"
            enterFrom="-translate-x-full"
            enterTo="translate-x-0"
            leave="transition ease-in-out duration-300 transform"
            leaveFrom="translate-x-0"
            leaveTo="-translate-x-full"
          >
            <Dialog.Panel className="relative mr-16 flex w-full max-w-xs flex-1">
              <Transition.Child
                as={Fragment}
                enter="ease-in-out duration-300"
                enterFrom="opacity-0"
                enterTo="opacity-100"
                leave="ease-in-out duration-300"
                leaveFrom="opacity-100"
                leaveTo="opacity-0"
              >
                <div className="absolute left-full top-0 flex w-16 justify-center pt-5">
                  <button
                    type="button"
                    className="-m-2.5 p-2.5"
                    onClick={() => setOpen(false)}
                  >
                    <span className="sr-only">Close sidebar</span>
                    <XMarkIcon className="h-6 w-6 text-white" aria-hidden="true" />
                  </button>
                </div>
              </Transition.Child>
              
              <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-white">
                <SidebarContent 
                  onNavigate={() => setOpen(false)} 
                  isCollapsed={false} 
                  onToggleCollapse={() => {}} 
                />
              </div>
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition.Root>
  );
}

// Desktop sidebar
export function DesktopSidebar({ isCollapsed, onToggleCollapse }: { 
  isCollapsed: boolean; 
  onToggleCollapse: () => void; 
}) {
  return (
    <div className={`hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:flex-col transition-all duration-300 ${
      isCollapsed ? 'lg:w-16' : 'lg:w-72'
    }`}>
      <div className="flex grow flex-col gap-y-5 overflow-y-auto border-r border-gray-200 bg-white shadow-sm">
        <SidebarContent isCollapsed={isCollapsed} onToggleCollapse={onToggleCollapse} />
      </div>
    </div>
  );
}