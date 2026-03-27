/**
 * NavigationContext
 * Provides app-level navigation without prop drilling
 */

import { createContext, useContext } from 'react';

interface NavigationContextValue {
  navigateTo: (view: string, anchor?: string) => void;
}

export const NavigationContext = createContext<NavigationContextValue>({
  navigateTo: () => {},
});

export const useNavigation = () => useContext(NavigationContext);
