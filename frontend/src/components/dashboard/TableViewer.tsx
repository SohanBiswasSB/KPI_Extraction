'use client';

import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ExtractedTable {
  id: number;
  file_id: number;
  page: number;
  table_index: number;
  source: string | null;
  sheet_name: string | null;
  caption: string | null;
  n_rows: number;
  n_cols: number;
  confidence: number | null;
  rows: (string | number | null)[][];
}

interface TableViewerProps {
  fileId: number;
  /** Original filename, shown in the header and used for the export download name. */
  filename?: string;
  onClose?: () => void;
}

const SOURCE_LABELS: Record<string, string> = {
  pdfplumber: 'PDF (native)',
  ocr: 'PDF (OCR)',
  excel: 'Excel',
  csv: 'CSV',
  docx: 'Word',
};

/**
 * Fetches the structured tables extracted from a file and renders them as real
 * HTML tables, with a one-click XLSX export. Talks to the consolidated backend's
 * /api/v1/files/{id}/tables and /tables/export endpoints.
 */
export function TableViewer({ fileId, filename, onClose }: TableViewerProps) {
  const [tables, setTables] = useState<ExtractedTable[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const authHeader = () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/v1/files/${fileId}/tables`, {
          headers: { ...authHeader() },
        });
        if (!res.ok) throw new Error(`Failed to load tables (${res.status})`);
        const data: ExtractedTable[] = await res.json();
        if (active) setTables(data);
      } catch (e: any) {
        if (active) setError(e.message ?? 'Failed to load tables');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [fileId]);

  const handleExport = async () => {
    const res = await fetch(`${API_BASE}/api/v1/files/${fileId}/tables/export`, {
      headers: { ...authHeader() },
    });
    if (!res.ok) {
      setError(`Export failed (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(filename || `file_${fileId}`).replace(/\.[^.]+$/, '')}_tables.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-white rounded-lg shadow-lg border border-gray-200">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Extracted tables</h3>
          {filename && <p className="text-sm text-gray-500">{filename}</p>}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExport}
            disabled={loading || tables.length === 0}
            className="px-3 py-1.5 text-sm font-medium rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Export XLSX
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm font-medium rounded-md bg-gray-100 text-gray-700 hover:bg-gray-200"
            >
              Close
            </button>
          )}
        </div>
      </div>

      <div className="p-5 space-y-8 max-h-[70vh] overflow-y-auto">
        {loading && <p className="text-sm text-gray-500">Loading tables…</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!loading && !error && tables.length === 0 && (
          <p className="text-sm text-gray-500">No tables were extracted from this document.</p>
        )}

        {tables.map((t) => {
          const header = t.rows[0] ?? [];
          const body = t.rows.slice(1);
          return (
            <div key={t.id}>
              <div className="flex items-center gap-2 mb-2 text-xs text-gray-500">
                <span className="font-medium text-gray-700">
                  {t.sheet_name ? `Sheet "${t.sheet_name}"` : `Page ${t.page}`} · table {t.table_index + 1}
                </span>
                <span className="px-1.5 py-0.5 rounded bg-gray-100">
                  {SOURCE_LABELS[t.source ?? ''] ?? t.source ?? 'unknown'}
                </span>
                <span>{t.n_rows}×{t.n_cols}</span>
                {t.confidence != null && t.confidence < 0.7 && (
                  <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
                    low confidence
                  </span>
                )}
              </div>
              <div className="overflow-x-auto border border-gray-200 rounded-md">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      {header.map((cell, ci) => (
                        <th key={ci} className="px-3 py-2 text-left font-semibold text-gray-700 whitespace-nowrap">
                          {cell == null ? '' : String(cell)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {body.map((row, ri) => (
                      <tr key={ri} className={ri % 2 ? 'bg-gray-50/50' : ''}>
                        {row.map((cell, ci) => (
                          <td key={ci} className="px-3 py-1.5 text-gray-700 whitespace-nowrap">
                            {cell == null ? '' : String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default TableViewer;
