'use client';

import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { 
  CloudArrowUpIcon, 
  DocumentIcon, 
  XMarkIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline';
import { fileApi } from '@/lib/api';
import { toast } from 'react-hot-toast';

interface FileUploadWidgetProps {
  organizationId: number;
}

export function FileUploadWidget({ organizationId }: FileUploadWidgetProps) {
  const [uploading, setUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setUploading(true);
    
    try {
      for (const file of acceptedFiles) {
        await fileApi.uploadFile(file, organizationId);
        setUploadedFiles(prev => [...prev, file]);
        toast.success(`${file.name} uploaded successfully!`);
      }
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Upload failed. Please try again.';
      toast.error(message);
    } finally {
      setUploading(false);
    }
  }, [organizationId]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/plain': ['.txt'],
      'text/csv': ['.csv'],
    },
    multiple: true,
  });

  const removeFile = (index: number) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="text-lg font-semibold text-secondary-900">
          Upload Documents
        </h3>
        <p className="text-sm text-secondary-600 mt-1">
          Upload PDF, Excel, or text files to extract KPIs
        </p>
      </div>
      <div className="card-body">
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
            isDragActive
              ? 'border-primary-400 bg-primary-50'
              : 'border-secondary-300 hover:border-primary-400 hover:bg-primary-50'
          }`}
        >
          <input {...getInputProps()} />
          <CloudArrowUpIcon className="mx-auto h-12 w-12 text-secondary-400" />
          <div className="mt-4">
            {isDragActive ? (
              <p className="text-primary-600 font-medium">Drop the files here...</p>
            ) : (
              <div>
                <p className="text-secondary-600">
                  Drag & drop files here, or{' '}
                  <span className="text-primary-600 hover:text-primary-500 cursor-pointer">
                    click to select
                  </span>
                </p>
                <p className="text-xs text-secondary-500 mt-2">
                  Supports PDF, Excel, CSV, and text files
                </p>
              </div>
            )}
          </div>
        </div>

        {uploading && (
          <div className="mt-4 flex items-center justify-center">
            <div className="loading-spinner loading-spinner-md mr-2" />
            <span className="text-sm text-secondary-600">Processing files...</span>
          </div>
        )}

        {uploadedFiles.length > 0 && (
          <div className="mt-4">
            <h4 className="text-sm font-medium text-secondary-900 mb-2">
              Recently Uploaded
            </h4>
            <div className="space-y-2">
              {uploadedFiles.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-2 bg-secondary-50 rounded-md"
                >
                  <div className="flex items-center space-x-2">
                    <DocumentIcon className="h-4 w-4 text-secondary-500" />
                    <span className="text-sm text-secondary-700 truncate">
                      {file.name}
                    </span>
                    <CheckCircleIcon className="h-4 w-4 text-success-500" />
                  </div>
                  <button
                    onClick={() => removeFile(index)}
                    className="text-secondary-400 hover:text-secondary-600"
                  >
                    <XMarkIcon className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 text-xs text-secondary-500">
          <p>• Files will be processed automatically to extract KPIs</p>
          <p>• Maximum file size: 50MB</p>
          <p>• Supported formats: PDF, Excel (.xlsx, .xls), CSV, TXT</p>
        </div>
      </div>
    </div>
  );
} 