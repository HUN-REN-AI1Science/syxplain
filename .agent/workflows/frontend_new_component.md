---
description: Guide for adding new React components to the frontend
---

# Frontend: Add New Component

This workflow outlines the standard process for creating and integrating new React components into the Syxplain frontend.

## 1. Component Classification & Location
Determine where the component belongs based on its reusability and scope.

- **Feature-Specific**: Components used only within a specific feature context.
  - **Path**: `frontend/src/components/<FeatureName>/<ComponentName>.tsx`
  - **Example**: `EquationResults/EquationCard.tsx`
- **Common/Shared**: Reusable UI elements used across multiple pages.
  - **Path**: `frontend/src/components/common/<ComponentName>.tsx`
  - **Example**: `common/StatusBadge.tsx`
- **Page Sections**: Large sections of a page that are extracted for readability.
  - **Path**: Same as Feature-Specific.

## 2. Component Implementation Structure
Follow this template for consistency. Usage of **PrimeReact** components and **Tailwind CSS** is mandatory.

```tsx
import React from 'react';
import { Button } from 'primereact/button'; // Import PrimeReact components
import type { MyData } from '@/types'; // Use type aliases

// 1. Define Props Interface
interface MyComponentProps {
  title: string;
  data: MyData;
  onAction: (id: string) => void;
  className?: string; // Always allow custom styling injection
}

// 2. Functional Component Definition
export const MyComponent: React.FC<MyComponentProps> = ({
  title,
  data,
  onAction,
  className = ''
}) => {
  // 3. Render using Tailwind for layout and PrimeReact for widgets
  return (
    <div className={`p-4 bg-white rounded-lg shadow-sm ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
        <Button
          icon="pi pi-check"
          size="small"
          onClick={() => onAction(data.id)}
        />
      </div>
      <div className="text-slate-600">
        {/* Content */}
      </div>
    </div>
  );
};
```

## 3. Styling Rules
- **Framework**: PrimeReact (Buttons, Tables, Dialogs, Inputs).
- **Layout/Spacing**: Tailwind CSS (`flex`, `grid`, `p-4`, `gap-2`).
- **Colors**: Use `slate` for neutrals (text-slate-800, border-slate-200). Use semantic PrimeReact severities (`success`, `danger`) where applicable.
- **Responsiveness**: Use Tailwind breakdown prefixes (`sm:`, `md:`, `lg:`).

## 4. Integration
1.  **Import**: Use path aliases.
    - `@services/*` -> specific services.
    - `@/*` -> root of src.
2.  **Place**: Add component to the parent page JSX.
3.  **Wire**: Pass props and event handlers.

## 5. State Management
- If component has local state, use `useState`.
- If component needs data fetching, invoke it in the **Parent Page** and pass data down via props, OR use a custom hook in `frontend/src/hooks` if logic is complex/reusable.
- Avoid making API calls directly inside presentational components.
