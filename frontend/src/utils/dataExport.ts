/**
 * Data Export Utility
 * Exports measured and predicted values from equation analysis results to CSV or Excel
 */

import * as XLSX from 'xlsx';
import type { Equation } from '@/types';

interface ExportRow {
  equation_id: number;
  equation: string;
  measured: number;
  predicted: number;
}

/**
 * Prepare export data from equations
 * Combines scatter_data from all equations into a flat array of rows
 */
function prepareExportData(equations: Equation[]): ExportRow[] {
  const rows: ExportRow[] = [];

  for (const eq of equations) {
    if (!eq.scatter_data) continue;

    const { measured, predicted } = eq.scatter_data;
    const count = Math.min(measured.length, predicted.length);

    for (let i = 0; i < count; i++) {
      rows.push({
        equation_id: eq.id,
        equation: eq.equation,
        measured: measured[i],
        predicted: predicted[i],
      });
    }
  }

  return rows;
}

/**
 * Export equation data to CSV format
 */
export function exportToCSV(equations: Equation[], runId: string): void {
  const rows = prepareExportData(equations);

  if (rows.length === 0) {
    throw new Error('No scatter data available to export');
  }

  // Create CSV content
  const headers = ['equation_id', 'equation', 'measured', 'predicted'];
  const csvContent = [
    headers.join(','),
    ...rows.map(row =>
      `${row.equation_id},"${row.equation.replace(/"/g, '""')}",${row.measured},${row.predicted}`
    )
  ].join('\n');

  // Download file
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, `analysis_data_${runId.slice(0, 8)}.csv`);
}

/**
 * Export equation data to Excel format
 */
export function exportToExcel(equations: Equation[], runId: string): void {
  const rows = prepareExportData(equations);

  if (rows.length === 0) {
    throw new Error('No scatter data available to export');
  }

  // Create workbook and worksheet
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Analysis Data');

  // Set column widths
  ws['!cols'] = [
    { wch: 12 },  // equation_id
    { wch: 40 },  // equation
    { wch: 15 },  // measured
    { wch: 15 },  // predicted
  ];

  // Generate and download
  const buffer = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
  const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  downloadBlob(blob, `analysis_data_${runId.slice(0, 8)}.xlsx`);
}

/**
 * Helper function to trigger file download
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
