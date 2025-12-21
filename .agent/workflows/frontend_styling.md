---
description: Guidelines for frontend styling and component usage
---

# Frontend Styling Guidelines

The frontend uses **React (Vite)** with **PrimeReact** and **Tailwind CSS**.

## Button Components

**NEVER** use a plain HTML `<button>` tag or create a custom button style from scratch unless explicitly requested.

**ALWAYS** use the `Button` component from PrimeReact:

```tsx
import { Button } from 'primereact/button';

// Usage
<Button label="Click Me" icon="pi pi-check" onClick={handleClick} />
<Button label="Cancel" className="p-button-secondary" />
<Button label="Delete" className="p-button-danger" />
```

## Styling Principles

1.  **PrimeReact First**: Use PrimeReact components (`InputText`, `Dialog`, `Card`, etc.) as the primary building blocks.
2.  **Tailwind Utilities**: Use Tailwind CSS for layout (flex, grid, padding, margin) and typography colors.
3.  **Global Styles**: Check `src/index.css` for global overrides.
4.  **Consistency**: Match existing UI patterns. Do not invent new color schemes or component styles.
5.  **Colors**:
    *   **Primary**: Use "Syxplain Blue" (`#0052cc` / `blue-600` range) for primary actions and accents.
    *   **Forbidden**: Do NOT use purple, pink, or arbitrary colors. Stick to the blue/slate/white/gray palette.
    *   **Shapes**: Use consistent border radius (rounded-md/lg) matching existing components.

## New Components

When creating a new component:
1.  Check if a PrimeReact component exists for the purpose.
2.  Use `Button` for all actions.
3.  Ensure responsiveness using Tailwind breakpoints (`md:`, `lg:`).
