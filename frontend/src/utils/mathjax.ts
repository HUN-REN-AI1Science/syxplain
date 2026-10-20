/**
 * Shared MathJax (AsciiMath) configuration for equation rendering
 */

export const mathJaxConfig = {
  loader: { load: ['input/asciimath', 'output/chtml'] },
  asciimath: {
    displaystyle: true,
    delimiters: [['`', '`']],
  },
  options: {
    // Disable automatic typesetting on page load
    skipHtmlTags: [
      'script',
      'noscript',
      'style',
      'textarea',
      'pre',
      'code',
      'annotation',
      'annotation-xml',
    ],
  },
  startup: {
    // Disable automatic document typesetting - critical to prevent processing description text
    typeset: false,
  },
};
