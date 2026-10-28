/**
 * PDF Export Utility
 * Generates professional PDF reports from equation analysis results
 */

import jsPDF from 'jspdf';
import {
  asText,
  basisOf,
  COHERENCE_LABEL,
  COHERENCE_OVERALL_LABEL,
  domainChecksOf,
  fmtCeiling,
  headlineReasonText,
  KNOWN_LAW_COMPARISON_TEXT,
  KNOWN_LAW_RELATION_LABEL,
  metricLabel,
  metricValue,
  rejectedFormText,
  scatterBasisLabel,
  variableLegend,
} from '@utils/discovery';
import type {
  CoherenceReport,
  DiscoveryReport,
  DomainCoherence,
  EquationResults,
  Equation,
  RunWarning,
} from '@/types';

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
// Text Sanitising
// ============================================================================

/** Replacements for common characters the standard PDF fonts (WinAnsi) cannot draw */
const WINANSI_REPLACEMENTS: Record<string, string> = {
  '≈': '~',
  '→': '->',
  '←': '<-',
  '↔': '<->',
  '⇒': '=>',
  '≥': '>=',
  '≤': '<=',
  '≠': '!=',
  '×': 'x',
  '−': '-',
  '—': '-',
  '–': '-',
  '‐': '-',
  '‑': '-',
  '‘': "'",
  '’': "'",
  '‚': ',',
  '‛': "'",
  '“': '"',
  '”': '"',
  '„': '"',
  '′': "'",
  '″': '"',
  '√': 'sqrt',
  '∞': 'inf',
  '∑': 'sum',
  '∂': 'd',
  '∝': '~',
  '⋅': '·',
  '∙': '·',
  '\u00a0': ' ',
  '\u2009': ' ',
  '\u202f': ' ',
  '\u200b': '',
  α: 'alpha',
  β: 'beta',
  γ: 'gamma',
  δ: 'delta',
  Δ: 'Delta',
  ε: 'epsilon',
  θ: 'theta',
  κ: 'kappa',
  λ: 'lambda',
  μ: 'µ',
  ν: 'nu',
  π: 'pi',
  ρ: 'rho',
  σ: 'sigma',
  Σ: 'Sigma',
  τ: 'tau',
  φ: 'phi',
  χ: 'chi',
  ψ: 'psi',
  ω: 'omega',
  Ω: 'Omega',
  '⁰': '^0',
  '⁴': '^4',
  '⁵': '^5',
  '⁶': '^6',
  '⁷': '^7',
  '⁸': '^8',
  '⁹': '^9',
  '⁻': '^-',
  '₀': '0',
  '₁': '1',
  '₂': '2',
  '₃': '3',
};

/** Windows-1252 characters outside Latin-1 that the standard fonts can draw */
const CP1252_EXTRAS = new Set('€ƒ…†‡ˆ‰Š‹ŒŽ•˜™š›œžŸ');

const isWinAnsi = (ch: string): boolean => {
  const code = ch.codePointAt(0) ?? 0;
  return (
    code === 0x0a ||
    code === 0x09 ||
    (code >= 0x20 && code <= 0x7e) ||
    (code >= 0xa0 && code <= 0xff) ||
    CP1252_EXTRAS.has(ch)
  );
};

/**
 * Maps text to characters the standard PDF fonts can render (WinAnsi): common math symbols
 * become ASCII ("≈" -> "~", "→" -> "->", "σ" -> "sigma"), anything else unrenderable becomes "?".
 * Keeps WinAnsi characters such as ² ³ ± ° µ.
 */
export const sanitizeWinAnsi = (text: string): string => {
  let out = '';
  // for..of iterates code points, so an emoji becomes a single "?"
  for (const ch of text.normalize('NFC')) {
    if (ch in WINANSI_REPLACEMENTS) out += WINANSI_REPLACEMENTS[ch];
    else out += isWinAnsi(ch) ? ch : '?';
  }
  return out;
};

const w = (x: unknown): string => sanitizeWinAnsi(asText(x));

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

  if (!text) return;

  pdf.setFontSize(fontSize);
  pdf.setFont('times', isBold ? 'bold' : 'normal');
  pdf.setTextColor(color[0], color[1], color[2]);

  const lineHeightFactor = 0.5;
  const lines = pdf.splitTextToSize(sanitizeWinAnsi(text), contentWidth - 2);

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

/** "lhs = rhs" with the equation's own target alias on the left when it has one */
function equationText(eq: Equation, targetVariable?: string | null): string {
  const lhs = eq.target_alias || targetVariable;
  return w(lhs ? `${lhs} = ${eq.equation}` : eq.equation);
}

/** "where k = col_a, P = col_b" legend of the aliases an equation uses */
function legendText(eq: Equation): string {
  const pairs = variableLegend(eq.variables);
  return pairs.length ? `where ${pairs.map(([a, c]) => `${a} = ${c}`).join(', ')}` : '';
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
  const { pdf, margin } = ctx;

  renderSectionHeading(ctx, 'Analysis Summary');

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
  recommendation: EquationResults['recommendation'] | undefined,
  equations: Equation[],
  targetVariable?: string | null,
  headlineReason?: string
): void {
  const { pdf, margin, contentWidth } = ctx;

  // The selector's headline is the recommended model; older runs use the explainer's pick
  const headline = equations?.find((eq) => eq.is_headline);
  const recommendedId = headline?.id ?? recommendation?.equation_id ?? 0;
  if (recommendedId <= 0) return;

  const recEq = equations?.find((eq) => eq.id === recommendedId);
  const rationale =
    recommendation && recommendation.equation_id === recommendedId
      ? (recommendation.rationale ?? []).map((r) => w(r))
      : [];
  const reasonText = headline ? w(headlineReasonText(headlineReason)) : '';

  const recStartY = ctx.y;

  // Estimate height
  let recHeight = 35;
  if (recEq) {
    pdf.setFontSize(12);
    pdf.setFont('times', 'italic');
    const lines = pdf.splitTextToSize(equationText(recEq, targetVariable), contentWidth - 10);
    recHeight += lines.length * 6 + 10;
  }

  if (rationale.length > 0) {
    pdf.setFontSize(10);
    pdf.setFont('times', 'normal');
    let rationaleHeight = 6;
    rationale.forEach((reason) => {
      const lines = pdf.splitTextToSize(`• ${reason}`, contentWidth - 10);
      rationaleHeight += lines.length * 6;
    });
    recHeight += rationaleHeight;
  }
  if (reasonText) recHeight += 8;

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
    pdf.text(
      `Equation ${recEq.id}${recEq.model_id ? ` (${w(recEq.model_id)})` : ''}`,
      margin + 2,
      ctx.y
    );
    ctx.y += 6;

    pdf.setFontSize(12);
    pdf.setFont('times', 'italic');
    pdf.setTextColor(40, 40, 40);
    const eqLines = pdf.splitTextToSize(equationText(recEq, targetVariable), contentWidth - 10);
    eqLines.forEach((line: string) => {
      pdf.text(line, margin + 5, ctx.y);
      ctx.y += 6;
    });
  }

  if (rationale.length > 0) {
    ctx.y += 3;
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(60, 60, 60);
    pdf.text('Selection Rationale:', margin + 2, ctx.y);
    ctx.y += 5;

    rationale.forEach((reason) => {
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

  if (reasonText) {
    ctx.y += 2;
    pdf.setFontSize(9);
    pdf.setFont('times', 'italic');
    pdf.setTextColor(80, 80, 80);
    pdf
      .splitTextToSize(`Model selection: ${reasonText}`, contentWidth - 10)
      .forEach((line: string) => {
        pdf.text(line, margin + 2, ctx.y);
        ctx.y += 5;
      });
  }
  ctx.y += 10;

  // The explanation AI may prefer another equation than the selector's headline
  if (
    headline &&
    recommendation?.agrees_with_headline === false &&
    recommendation.equation_id > 0 &&
    recommendation.equation_id !== headline.id
  ) {
    addText(
      ctx,
      `The explanation AI prefers Equation ${recommendation.equation_id}` +
        (recommendation.disagreement_reason ? `: ${w(recommendation.disagreement_reason)}` : '.'),
      10,
      false,
      [40, 40, 40]
    );
    ctx.y += 4;
  }
}

function renderEquation(
  ctx: PdfContext,
  eq: Equation,
  idx: number,
  totalCount: number,
  targetVariable: string | null | undefined,
  isRecommended: boolean
): void {
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
  const markers = [
    eq.model_id ? w(eq.model_id) : '',
    isRecommended ? 'Recommended' : '',
    eq.agent_recommended ? 'Agent pick' : '',
  ].filter(Boolean);
  pdf.text(
    `Equation Model ${eq.id}${markers.length ? `  (${markers.join(', ')})` : ''}`,
    margin + 14,
    ctx.y + 1
  );
  ctx.y += 7;

  // Metrics
  const r2 = metricValue(eq);
  const lossStr = typeof eq.loss === 'number' ? eq.loss.toFixed(4) : 'N/A';
  const complexityStr = eq.complexity != null ? String(eq.complexity) : 'N/A';
  const metrics = [
    r2 !== null ? `${metricLabel(eq.metric_basis, eq.holdout_n)}: ${r2.toFixed(3)}` : '',
    `Loss: ${lossStr}`,
    `Complexity: ${complexityStr}`,
  ].filter(Boolean);
  addText(ctx, metrics.join('   |   '), 9, false, [80, 80, 80]);
  ctx.y += 2;

  // Equation box
  pdf.setFillColor(250, 250, 250);
  pdf.setDrawColor(230, 230, 230);

  pdf.setFontSize(10);
  pdf.setFont('times', 'italic');
  pdf.setTextColor(0, 0, 0);
  const eqText = pdf.splitTextToSize(equationText(eq, targetVariable), contentWidth - 10);
  const boxHeight = Math.max(12, eqText.length * 6 + 6);

  pdf.rect(margin, ctx.y - 3, contentWidth, boxHeight, 'FD');

  let textY = ctx.y + 4;
  eqText.forEach((line: string) => {
    pdf.text(line, contentWidth / 2 + margin, textY, { align: 'center' });
    textY += 6;
  });
  ctx.y += boxHeight + 4;

  const legend = legendText(eq);
  if (legend) {
    addText(ctx, legend, 9, false, [90, 90, 90]);
  }
  ctx.y += 2;

  // Overview
  if (eq.overview) {
    addText(ctx, asText(eq.overview), 10, false, [40, 40, 40], 'justify');
    ctx.y += 2;
  }

  if (eq.agent_recommended && eq.agent_why) {
    addText(ctx, `Why the agent picked it: ${asText(eq.agent_why)}`, 9, false, [60, 60, 60]);
    ctx.y += 2;
  }

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

      const termPrefix = `${w(term.term)}: `;
      pdf.setFontSize(10);
      pdf.setFont('times', 'bold');
      pdf.setTextColor(0, 0, 0);
      const prefixWidth = pdf.getTextWidth(termPrefix);
      pdf.text(termPrefix, margin + 4, ctx.y);

      pdf.setFont('times', 'normal');
      pdf.setTextColor(60, 60, 60);

      const explanationLines = pdf.splitTextToSize(
        w(term.explanation),
        contentWidth - prefixWidth - 4
      );
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
      pdf.text(`[${cIdx + 1}] ${w(citation)}`, margin + 4, ctx.y);
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
    const basisText = scatterBasisLabel(eq.scatter_data);
    pdf.text(`Predicted vs. Measured${basisText ? ` (${basisText})` : ''}`, margin, ctx.y);
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

function renderEquations(
  ctx: PdfContext,
  equations: Equation[],
  targetVariable: string | null | undefined,
  recommendedId: number
): void {
  const { pdf } = ctx;

  if (!equations?.length) return;

  pdf.addPage();
  ctx.y = 30;

  renderSectionHeading(ctx, 'Detailed Equation Analysis');
  ctx.y += 4;

  equations.forEach((eq, idx) => {
    renderEquation(ctx, eq, idx, equations.length, targetVariable, eq.id === recommendedId);
  });
}

function renderSectionHeading(ctx: PdfContext, title: string): void {
  const { pdf, margin, pageWidth } = ctx;
  pdf.setFontSize(14);
  pdf.setFont('helvetica', 'bold');
  pdf.setTextColor(BRAND_COLORS.blue[0], BRAND_COLORS.blue[1], BRAND_COLORS.blue[2]);
  pdf.text(sanitizeWinAnsi(title), margin, ctx.y);
  pdf.setDrawColor(200, 200, 200);
  pdf.setLineWidth(0.2);
  pdf.line(margin, ctx.y + 2, pageWidth - margin, ctx.y + 2);
  ctx.y += 8;
}

function renderSubheading(ctx: PdfContext, title: string): void {
  checkPageBreak(ctx, 20);
  ctx.pdf.setFontSize(10);
  ctx.pdf.setFont('helvetica', 'bold');
  ctx.pdf.setTextColor(40, 40, 40);
  ctx.pdf.text(sanitizeWinAnsi(title), ctx.margin, ctx.y);
  ctx.y += 5;
}

function renderCoherence(
  ctx: PdfContext,
  report: CoherenceReport,
  domain: DomainCoherence | null | undefined
): void {
  checkPageBreak(ctx, 40);
  renderSectionHeading(ctx, 'Coherence of the Recommended Equation');

  addText(
    ctx,
    `Overall: ${COHERENCE_OVERALL_LABEL[report.overall] ?? w(report.overall)} (${w(report.model_id)})`,
    10,
    true,
    [20, 20, 20]
  );
  for (const c of Array.isArray(report.checks) ? report.checks : []) {
    addText(
      ctx,
      `${w(c.label)} (${COHERENCE_LABEL[c.status] ?? w(c.status)}): ${w(c.detail)}`,
      9,
      false,
      [60, 60, 60]
    );
  }
  const domainChecks = domainChecksOf(domain);
  if (domainChecks.length > 0 || domain?.assessment) {
    ctx.y += 3;
    renderSubheading(ctx, 'Domain plausibility (AI assessment)');
    for (const d of domainChecks) {
      addText(ctx, `${w(d.aspect)} (${w(d.status)}): ${w(d.explanation)}`, 9, false, [60, 60, 60]);
    }
    if (domain?.assessment) {
      addText(ctx, w(domain.assessment), 10, false, [20, 20, 20], 'justify');
    }
  }
  ctx.y += 6;
}

function renderDiscovery(ctx: PdfContext, report: DiscoveryReport): void {
  const r2 = (v: number | null | undefined) => (typeof v === 'number' ? v.toFixed(3) : '-');
  const list = <T>(x: T[] | null | undefined): T[] => (Array.isArray(x) ? x : []);
  const agent = report.agent ?? ({} as Partial<DiscoveryReport['agent']>);
  const split = report.split ?? { complete_rows: 0, train: 0, holdout: 0, scored_on: '' };
  const leaderboard = list(report.leaderboard);
  const basis = basisOf(split.metric_basis ?? leaderboard[0]?.metric_basis);
  const ceiling = fmtCeiling(report.noise_ceiling_r2, report.noise_ceiling_sd);

  checkPageBreak(ctx, 40);
  renderSectionHeading(ctx, 'How the Equations Were Found');

  if (report.has_signal === false) {
    addText(
      ctx,
      'No detectable relationship: even a flexible model cannot predict the target from these ' +
        `variables (noise-ceiling R² ${ceiling}).`,
      10,
      true,
      [160, 30, 30]
    );
  }
  if (agent.source === 'auto_fallback') {
    addText(
      ctx,
      'The agent did not write a final report; this summary was assembled automatically from its session.',
      9,
      false,
      [120, 90, 20]
    );
  }
  if (agent.summary) {
    addText(ctx, asText(agent.summary), 10, false, [20, 20, 20], 'justify');
  }
  const lateSearches = list(agent.late_searches);
  if (lateSearches.length > 0 || agent.stale) {
    addText(
      ctx,
      `Searches finished after the agent stopped${lateSearches.length ? `: ${lateSearches.join(', ')}` : ''}; ` +
        'their best models are included in the leaderboard but were not reviewed by the agent.',
      9,
      false,
      [90, 90, 90]
    );
  }

  const scoring =
    basis === 'cv'
      ? 'The dataset is too small for a holdout: all models are scored by cross-validation.'
      : `All models scored on ${split.holdout || split.train} held-out rows (${split.scored_on}).`;
  const rows =
    typeof split.uploaded === 'number'
      ? ` ${split.complete_rows} of ${split.uploaded} rows complete` +
        (split.dropped_incomplete
          ? ` (${split.dropped_incomplete} dropped for missing values).`
          : '.')
      : '';
  addText(
    ctx,
    `Noise ceiling (best achievable R², estimated): ${ceiling}. ${scoring}${rows}`,
    9,
    false,
    [90, 90, 90]
  );
  list(split.excluded_columns).forEach((c) =>
    addText(ctx, `Excluded column ${asText(c.column)}: ${asText(c.reason)}`, 9, false, [90, 90, 90])
  );
  ctx.y += 2;

  const nTotal = report.n_models_total ?? leaderboard.length;
  const shown = Math.min(10, leaderboard.length);
  renderSubheading(
    ctx,
    `Model leaderboard (top ${shown} of ${nTotal}; ${metricLabel(basis, split.holdout || null)})`
  );
  const headlineId = report.selection?.headline_model_id;
  leaderboard.slice(0, 10).forEach((entry, i) => {
    checkPageBreak(ctx, 20);
    const marks = [
      entry.is_headline || entry.model_id === headlineId ? 'recommended' : '',
      entry.agent_recommended ? 'agent pick' : '',
    ].filter(Boolean);
    addText(
      ctx,
      `${i + 1}. ${entry.model_id} ${asText(entry.label)} [${entry.kind}]${marks.length ? ` (${marks.join(', ')})` : ''} ` +
        `on ${list(entry.features).join(', ')}: R² ${r2(metricValue(entry))}, complexity ${entry.complexity}`,
      9,
      true,
      [30, 30, 30]
    );
    addText(ctx, entry.equation, 9, false, [60, 60, 60]);
    const reasons = list(entry.reasons).map(asText).filter(Boolean);
    if (reasons.length > 0) {
      addText(ctx, `Diagnosis: ${reasons.slice(0, 3).join('; ')}`, 9, false, [90, 90, 90]);
    }
  });

  const rejected = [
    ...list(agent.rejected_forms).map(rejectedFormText),
    ...list(report.notebook)
      .filter((n) => n.kind === 'rejected_form')
      .map((n) => asText(n.text)),
  ].filter(Boolean);
  if (rejected.length > 0) {
    ctx.y += 3;
    renderSubheading(ctx, "Why these laws didn't fit");
    rejected.forEach((text) => addText(ctx, `- ${text}`, 9, false, [40, 40, 40]));
  }

  const insights = [
    ...list(agent.insights).map(asText),
    ...list(report.notebook)
      .filter((n) => n.kind === 'insight')
      .map((n) => asText(n.text)),
  ].filter(Boolean);
  if (insights.length > 0) {
    ctx.y += 3;
    renderSubheading(ctx, 'Insights');
    insights.forEach((text) => addText(ctx, `- ${text}`, 9, false, [40, 40, 40]));
  }

  const questions = list(agent.open_questions).map(asText).filter(Boolean);
  if (questions.length > 0) {
    ctx.y += 3;
    renderSubheading(ctx, 'Open questions');
    questions.forEach((text) => addText(ctx, `- ${text}`, 9, false, [40, 40, 40]));
  }

  const relations = list(report.relations?.headline);
  if (relations.length > 0) {
    ctx.y += 3;
    renderSubheading(ctx, 'Relation to known laws (fitted after the discovery)');
    relations.forEach((r) => {
      addText(
        ctx,
        `- ${asText(r.label)} (${r.law_id}): ${KNOWN_LAW_RELATION_LABEL[r.relation] ?? r.relation}; ` +
          `${KNOWN_LAW_COMPARISON_TEXT[r.comparison] ?? ''} (CV R² ${r2(r.cv_r2)}), ` +
          `predictions agree R² ${r2(r.agreement_r2)}`,
        9,
        false,
        [40, 40, 40]
      );
    });
  }

  const laws = list(report.literature?.laws);
  if (laws.length > 0) {
    ctx.y += 3;
    renderSubheading(ctx, 'Published laws tested');
    laws.forEach((law) => {
      const unmapped = list(law.unmapped).map(asText).filter(Boolean);
      const fit =
        law.model_id && typeof law.cv_r2 === 'number'
          ? `fitted as ${law.model_id}: CV R² ${r2(law.cv_r2)}`
          : law.fit_error
            ? `not fitted: ${asText(law.fit_error)}`
            : unmapped.length
              ? `not fitted: unmapped variables ${unmapped.join(', ')}`
              : '';
      addText(ctx, `- ${asText(law.equation)}${fit ? ` (${fit})` : ''}`, 9, false, [40, 40, 40]);
      list(law.citations).forEach((c) => addText(ctx, `  ${asText(c)}`, 8, false, [0, 72, 180]));
    });
  }
  ctx.y += 6;
}

function renderWarnings(
  ctx: PdfContext,
  warnings: RunWarning[],
  explanationError: string | null
): void {
  if (explanationError !== null) {
    addText(
      ctx,
      `AI explanation unavailable${explanationError ? `: ${explanationError}` : ''}. ` +
        'The equations, scores and discovery report are complete; only the written interpretation is missing.',
      10,
      true,
      [150, 90, 0]
    );
  }
  warnings
    .filter((wn) => wn.stage !== 'explanation' && wn.message)
    .forEach((wn) => addText(ctx, `Note (${wn.stage}): ${wn.message}`, 9, false, [150, 90, 0]));
  if (explanationError !== null || warnings.length > 0) ctx.y += 4;
}

// ============================================================================
// Main Export Function
// ============================================================================

/**
 * Generate a PDF report from equation analysis results
 */
export async function generateResultsPdf(
  data: EquationResults,
  runId: string,
  targetVariable?: string | null,
  discovery?: DiscoveryReport | null,
  warnings: RunWarning[] = []
): Promise<void> {
  const { summary, recommendation } = data;
  const equations = Array.isArray(data.equations) ? data.equations : [];
  const ctx = createPdfContext();

  const explanationWarning = warnings.find((wn) => wn.stage === 'explanation');
  const explanationError =
    data._explanation_error || explanationWarning
      ? (explanationWarning?.message ?? data._explanation_error_message ?? '')
      : null;

  // Render sections
  renderHeader(ctx, runId);
  renderWarnings(ctx, warnings, explanationError);

  if (summary) {
    renderSummary(ctx, summary);
  }

  const headline = equations.find((eq) => eq.is_headline);
  renderRecommendation(
    ctx,
    recommendation,
    equations,
    targetVariable,
    discovery?.selection?.headline_reason
  );
  if (discovery?.coherence) {
    renderCoherence(ctx, discovery.coherence, data.coherence);
  }
  renderEquations(ctx, equations, targetVariable, headline?.id ?? recommendation?.equation_id ?? 0);

  if (discovery) {
    renderDiscovery(ctx, discovery);
  }

  // Add page footers
  addFooter(ctx);

  // Save the PDF
  ctx.pdf.save(`syxplain_results_${runId.slice(0, 8)}.pdf`);
}
