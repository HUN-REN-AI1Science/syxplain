/**
 * PDF Export Utility
 * Generates professional PDF reports from equation analysis results
 */

import jsPDF from 'jspdf';
import type { EquationResults, Equation } from '@/types';

// ============================================================================
// Constants
// ============================================================================

const BRAND_COLORS = {
  blue: [0, 72, 180] as const,
  green: [21, 128, 61] as const,
  lightGreen: [240, 253, 244] as const,
  lightGray: [250, 250, 250] as const,
};

const PAGE_SETTINGS = {
  orientation: 'portrait' as const,
  unit: 'mm' as const,
  format: 'a4' as const,
  margin: 20,
};

// ============================================================================
// Helper Functions
// ============================================================================

interface PdfContext {
  pdf: jsPDF;
  y: number;
  pageWidth: number;
  pageHeight: number;
  margin: number;
  contentWidth: number;
}

function createPdfContext(): PdfContext {
  const pdf = new jsPDF({
    orientation: PAGE_SETTINGS.orientation,
    unit: PAGE_SETTINGS.unit,
    format: PAGE_SETTINGS.format,
  });

  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const margin = PAGE_SETTINGS.margin;
  const contentWidth = pageWidth - 2 * margin;

  return { pdf, y: 30, pageWidth, pageHeight, margin, contentWidth };
}

function addFooter(ctx: PdfContext): void {
  const { pdf, pageWidth, pageHeight, margin } = ctx;
  const pageCount = pdf.getNumberOfPages();

  for (let i = 1; i <= pageCount; i++) {
    pdf.setPage(i);
    pdf.setFontSize(9);
    pdf.setTextColor(120, 120, 120);
    pdf.setFont('helvetica', 'normal');
    pdf.line(margin, pageHeight - 15, pageWidth - margin, pageHeight - 15);
    pdf.text(`Page ${i} of ${pageCount}`, pageWidth / 2, pageHeight - 8, { align: 'center' });
    pdf.text('Syxplain Analysis', pageWidth - margin, pageHeight - 8, { align: 'right' });
  }
}

function drawSectionCard(
  ctx: PdfContext,
  startY: number,
  height: number,
  accentColor: readonly number[] = BRAND_COLORS.blue,
  bgColor: readonly number[] = BRAND_COLORS.lightGray
): void {
  const { pdf, margin, contentWidth } = ctx;

  // Background
  pdf.setFillColor(bgColor[0], bgColor[1], bgColor[2]);
  pdf.roundedRect(margin - 3, startY - 5, contentWidth + 6, height + 10, 2, 2, 'F');

  // Left accent strip
  pdf.setFillColor(accentColor[0], accentColor[1], accentColor[2]);
  pdf.rect(margin - 3, startY - 5, 1.5, height + 10, 'F');
}

function addText(
  ctx: PdfContext,
  text: string,
  fontSize: number,
  isBold = false,
  color: readonly number[] = [0, 0, 0],
  align: 'left' | 'center' | 'right' | 'justify' = 'left'
): void {
  const { pdf, margin, contentWidth, pageHeight } = ctx;

  pdf.setFontSize(fontSize);
  pdf.setFont('times', isBold ? 'bold' : 'normal');
  pdf.setTextColor(color[0], color[1], color[2]);

  const lineHeightFactor = 0.5;
  const lines = pdf.splitTextToSize(text, contentWidth - 2);

  lines.forEach((line: string) => {
    if (ctx.y > pageHeight - margin - 10) {
      pdf.addPage();
      ctx.y = 30;
    }
    pdf.text(line, margin, ctx.y, { align });
    ctx.y += fontSize * lineHeightFactor + 1;
  });
  ctx.y += 2;
}

function checkPageBreak(ctx: PdfContext, requiredSpace: number): void {
  const { pdf, pageHeight, margin } = ctx;
  if (ctx.y > pageHeight - margin - requiredSpace) {
    pdf.addPage();
    ctx.y = 30;
  }
}

// ============================================================================
// Section Renderers
// ============================================================================

function renderHeader(ctx: PdfContext, runId: string): void {
  const { pdf, margin, pageWidth } = ctx;

  pdf.setDrawColor(BRAND_COLORS.blue[0], BRAND_COLORS.blue[1], BRAND_COLORS.blue[2]);
  pdf.setLineWidth(0.5);
  pdf.line(margin, 20, pageWidth - margin, 20);

  pdf.setFontSize(22);
  pdf.setFont('helvetica', 'bold');
  pdf.setTextColor(20, 20, 20);
  pdf.text('Analysis Report', margin, 16);

  pdf.setFontSize(10);
  pdf.setFont('helvetica', 'normal');
  pdf.setTextColor(80, 80, 80);
  pdf.text(`Run ID: ${runId.slice(0, 8)}`, pageWidth - margin, 12, { align: 'right' });
  pdf.text(`${new Date().toLocaleDateString()}`, pageWidth - margin, 17, { align: 'right' });

  ctx.y = 35;
}

function renderSummary(ctx: PdfContext, summary: EquationResults['summary']): void {
  const { pdf, margin, pageWidth } = ctx;

  // Section header
  pdf.setFontSize(14);
  pdf.setFont('helvetica', 'bold');
  pdf.setTextColor(BRAND_COLORS.blue[0], BRAND_COLORS.blue[1], BRAND_COLORS.blue[2]);
  pdf.text('Analysis Summary', margin, ctx.y);
  pdf.setDrawColor(200, 200, 200);
  pdf.setLineWidth(0.2);
  pdf.line(margin, ctx.y + 2, pageWidth - margin, ctx.y + 2);

  ctx.y += 8;

  if (summary.key_drivers?.length > 0) {
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(40, 40, 40);
    pdf.text('Primary Drivers:', margin, ctx.y);
    ctx.y += 5;

    addText(ctx, summary.key_drivers.join(', '), 10, false, [20, 20, 20]);
    ctx.y += 3;
  }

  if (summary.secondary_drivers?.length > 0) {
    ctx.y += 3;
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(40, 40, 40);
    pdf.text('Secondary Drivers:', margin, ctx.y);
    ctx.y += 5;

    addText(ctx, summary.secondary_drivers.join(', '), 10, false, [60, 60, 60]);
    ctx.y += 3;
  }

  if (summary.findings) {
    ctx.y += 5;
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(40, 40, 40);
    pdf.text('Key Findings:', margin, ctx.y);
    ctx.y += 5;
    addText(ctx, summary.findings, 10, false, [20, 20, 20], 'justify');
    ctx.y += 6;
  }
  ctx.y += 6;
}

function renderRecommendation(
  ctx: PdfContext,
  recommendation: EquationResults['recommendation'],
  equations: Equation[]
): void {
  const { pdf, margin, contentWidth } = ctx;

  if (!recommendation || recommendation.equation_id <= 0) return;

  const recStartY = ctx.y;
  const recEq = equations?.find((eq) => eq.id === recommendation.equation_id);

  // Estimate height
  let recHeight = 35;
  if (recEq) {
    pdf.setFontSize(12);
    pdf.setFont('times', 'italic');
    const lines = pdf.splitTextToSize(recEq.equation, contentWidth - 10);
    recHeight += lines.length * 6 + 10;
  }

  if (recommendation.rationale?.length > 0) {
    pdf.setFontSize(10);
    pdf.setFont('times', 'normal');
    let rationaleHeight = 6;
    recommendation.rationale.forEach((reason: string) => {
      const lines = pdf.splitTextToSize(`• ${reason}`, contentWidth - 10);
      rationaleHeight += lines.length * 6;
    });
    recHeight += rationaleHeight;
  }

  drawSectionCard(ctx, recStartY, recHeight, BRAND_COLORS.green, BRAND_COLORS.lightGreen);

  pdf.setFontSize(12);
  pdf.setFont('helvetica', 'bold');
  pdf.setTextColor(BRAND_COLORS.green[0], BRAND_COLORS.green[1], BRAND_COLORS.green[2]);
  pdf.text('RECOMMENDED MODEL', margin + 2, ctx.y);
  ctx.y += 8;

  if (recEq) {
    pdf.setFontSize(11);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(20, 20, 20);
    pdf.text(`Equation ${recEq.id}`, margin + 2, ctx.y);
    ctx.y += 6;

    pdf.setFontSize(12);
    pdf.setFont('times', 'italic');
    pdf.setTextColor(40, 40, 40);
    const eqLines = pdf.splitTextToSize(recEq.equation, contentWidth - 10);
    eqLines.forEach((line: string) => {
      pdf.text(line, margin + 5, ctx.y);
      ctx.y += 6;
    });
  }

  if (recommendation.rationale?.length > 0) {
    ctx.y += 3;
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(60, 60, 60);
    pdf.text('Selection Rationale:', margin + 2, ctx.y);
    ctx.y += 5;

    recommendation.rationale.forEach((reason: string) => {
      pdf.setFontSize(10);
      pdf.setFont('times', 'normal');
      pdf.setTextColor(40, 40, 40);
      const rLines = pdf.splitTextToSize(`• ${reason}`, contentWidth - 10);
      rLines.forEach((line: string) => {
        pdf.text(line, margin + 5, ctx.y);
        ctx.y += 5;
      });
    });
  }
  ctx.y += 10;
}

function renderEquation(ctx: PdfContext, eq: Equation, idx: number, totalCount: number): void {
  const { pdf, margin, pageWidth, contentWidth } = ctx;

  checkPageBreak(ctx, 60);

  // Equation number and metrics line
  pdf.setFillColor(BRAND_COLORS.blue[0], BRAND_COLORS.blue[1], BRAND_COLORS.blue[2]);
  pdf.roundedRect(margin, ctx.y - 4, 10, 8, 2, 2, 'F');
  pdf.setFontSize(10);
  pdf.setFont('helvetica', 'bold');
  pdf.setTextColor(255, 255, 255);
  pdf.text(String(eq.id), margin + 5, ctx.y + 1.5, { align: 'center' });

  pdf.setFontSize(12);
  pdf.setTextColor(20, 20, 20);
  pdf.text(`Equation Model ${eq.id}`, margin + 14, ctx.y + 1);

  // Metrics
  pdf.setFontSize(9);
  pdf.setFont('helvetica', 'normal');
  pdf.setTextColor(80, 80, 80);
  const metrics = `Loss: ${eq.loss.toFixed(4)}   |   Complexity: ${eq.complexity}`;
  pdf.text(metrics, pageWidth - margin, ctx.y + 1, { align: 'right' });

  ctx.y += 8;

  // Equation box
  pdf.setFillColor(250, 250, 250);
  pdf.setDrawColor(230, 230, 230);

  pdf.setFontSize(10);
  pdf.setFont('times', 'italic');
  pdf.setTextColor(0, 0, 0);
  const eqText = pdf.splitTextToSize(eq.equation, contentWidth - 10);
  const boxHeight = Math.max(12, eqText.length * 6 + 6);

  pdf.rect(margin, ctx.y - 3, contentWidth, boxHeight, 'FD');

  let textY = ctx.y + 4;
  eqText.forEach((line: string) => {
    pdf.text(line, contentWidth / 2 + margin, textY, { align: 'center' });
    textY += 6;
  });
  ctx.y += boxHeight + 6;

  // Overview
  addText(ctx, eq.overview, 10, false, [40, 40, 40], 'justify');
  ctx.y += 2;

  // Term Breakdown
  if (eq.term_explanations && eq.term_explanations.length > 0) {
    ctx.y += 2;
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(BRAND_COLORS.blue[0], BRAND_COLORS.blue[1], BRAND_COLORS.blue[2]);
    pdf.text('Term Interpretation', margin, ctx.y);
    ctx.y += 6;

    eq.term_explanations.forEach((term) => {
      checkPageBreak(ctx, 20);

      const termPrefix = `${term.term}: `;
      pdf.setFontSize(10);
      pdf.setFont('times', 'bold');
      pdf.setTextColor(0, 0, 0);
      const prefixWidth = pdf.getTextWidth(termPrefix);
      pdf.text(termPrefix, margin + 4, ctx.y);

      pdf.setFont('times', 'normal');
      pdf.setTextColor(60, 60, 60);

      const explanationLines = pdf.splitTextToSize(term.explanation, contentWidth - prefixWidth - 4);
      if (explanationLines.length > 0) {
        pdf.text(explanationLines[0], margin + 4 + prefixWidth, ctx.y);
        for (let i = 1; i < explanationLines.length; i++) {
          ctx.y += 5;
          pdf.text(explanationLines[i], margin + 4 + prefixWidth, ctx.y);
        }
      }
      ctx.y += 6;
    });
    ctx.y += 4;
  }

  // Citations
  if (eq.citations && eq.citations.length > 0) {
    checkPageBreak(ctx, 20);
    pdf.setFontSize(9);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(100, 100, 100);
    pdf.text('REFERENCES', margin, ctx.y);
    ctx.y += 5;

    eq.citations.forEach((citation, cIdx) => {
      checkPageBreak(ctx, 10);
      pdf.setFontSize(8);
      pdf.setFont('helvetica', 'normal');
      pdf.setTextColor(BRAND_COLORS.blue[0], BRAND_COLORS.blue[1], BRAND_COLORS.blue[2]);
      pdf.text(`[${cIdx + 1}] ${citation}`, margin + 4, ctx.y);
      ctx.y += 4;
    });
    ctx.y += 6;
  }

  // Scatter Plot
  if (eq.scatter_data && eq.scatter_data.measured.length > 0) {
    checkPageBreak(ctx, 60);

    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(40, 40, 40);
    pdf.text('Predicted vs. Measured', margin, ctx.y);
    ctx.y += 6;

    const chartX = margin + 10;
    const chartY = ctx.y;
    const chartSize = 50;

    // Chart background
    pdf.setFillColor(255, 255, 255);
    pdf.setDrawColor(180, 180, 180);
    pdf.setLineWidth(0.2);
    pdf.rect(chartX, chartY, chartSize, chartSize);

    // Grid lines
    pdf.setDrawColor(220, 220, 220);
    pdf.setLineDashPattern([1, 1], 0);
    for (let g = 1; g < 5; g++) {
      const gPos = g * (chartSize / 5);
      pdf.line(chartX + gPos, chartY, chartX + gPos, chartY + chartSize);
      pdf.line(chartX, chartY + gPos, chartX + chartSize, chartY + gPos);
    }
    pdf.setLineDashPattern([], 0);

    const allVals = [...eq.scatter_data.measured, ...eq.scatter_data.predicted];
    const minVal = Math.min(...allVals);
    const maxVal = Math.max(...allVals);
    const range = maxVal - minVal || 1;

    // 1:1 line
    pdf.setDrawColor(200, 50, 50);
    pdf.setLineWidth(0.3);
    pdf.line(chartX, chartY + chartSize, chartX + chartSize, chartY);

    // Scatter points
    pdf.setFillColor(BRAND_COLORS.blue[0], BRAND_COLORS.blue[1], BRAND_COLORS.blue[2]);
    const sampleRate = Math.max(1, Math.floor(eq.scatter_data.measured.length / 80));
    for (let i = 0; i < eq.scatter_data.measured.length; i += sampleRate) {
      const xNorm = (eq.scatter_data.measured[i] - minVal) / range;
      const yNorm = (eq.scatter_data.predicted[i] - minVal) / range;
      const px = chartX + xNorm * chartSize;
      const py = chartY + chartSize - yNorm * chartSize;
      pdf.circle(px, py, 0.7, 'F');
    }

    // Labels
    pdf.setFontSize(8);
    pdf.setTextColor(80, 80, 80);
    pdf.text('Measured', chartX + chartSize / 2, chartY + chartSize + 5, { align: 'center' });
    pdf.text('Predicted', chartX - 5, chartY + chartSize / 2, { angle: 90, align: 'center' });

    ctx.y = chartY + chartSize + 15;
  }

  // Separator line between equations
  if (idx < totalCount - 1) {
    pdf.setDrawColor(230, 230, 230);
    pdf.setLineWidth(0.3);
    pdf.line(margin, ctx.y, pageWidth - margin, ctx.y);
    ctx.y += 6;
  }
}

function renderEquations(ctx: PdfContext, equations: Equation[]): void {
  const { pdf, margin, pageWidth } = ctx;

  if (!equations?.length) return;

  pdf.addPage();
  ctx.y = 30;

  // Section header
  pdf.setFontSize(14);
  pdf.setFont('helvetica', 'bold');
  pdf.setTextColor(BRAND_COLORS.blue[0], BRAND_COLORS.blue[1], BRAND_COLORS.blue[2]);
  pdf.text('Detailed Equation Analysis', margin, ctx.y);

  pdf.setDrawColor(200, 200, 200);
  pdf.setLineWidth(0.2);
  pdf.line(margin, ctx.y + 2, pageWidth - margin, ctx.y + 2);

  ctx.y += 12;

  equations.forEach((eq, idx) => {
    renderEquation(ctx, eq, idx, equations.length);
  });
}

// ============================================================================
// Main Export Function
// ============================================================================

/**
 * Generate a PDF report from equation analysis results
 */
export async function generateResultsPdf(
  data: EquationResults,
  runId: string
): Promise<void> {
  const { equations, summary, recommendation } = data;
  const ctx = createPdfContext();

  // Render sections
  renderHeader(ctx, runId);

  if (summary) {
    renderSummary(ctx, summary);
  }

  renderRecommendation(ctx, recommendation, equations);
  renderEquations(ctx, equations);

  // Add page footers
  addFooter(ctx);

  // Save the PDF
  ctx.pdf.save(`syxplain_results_${runId.slice(0, 8)}.pdf`);
}
