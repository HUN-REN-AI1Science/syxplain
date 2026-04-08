/**
 * NavigationContext
 * Provides app-level navigation without prop drilling
 */

import { createContext, useContext } from 'react';

export type AppView = 'workflow' | 'history' | 'profile' | 'admin' | 'help';

interface NavigationContextValue {
  navigateTo: (view: AppView, anchor?: string) => void;
}

export const NavigationContext = createContext<NavigationContextValue>({
  navigateTo: () => {},
});

export const useNavigation = () => useContext(NavigationContext);
