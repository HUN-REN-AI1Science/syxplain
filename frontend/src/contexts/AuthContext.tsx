import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { useAuth as useOidcAuth } from 'react-oidc-context';
import { permissionsService, setTokenGetter, setSignOutHandler } from '@services/api';

interface AuthUser {
  id: string;
  email: string;
  name?: string;
  givenName?: string;
  familyName?: string;
}

interface AuthContextType {
  user: AuthUser | null;
  signIn: () => Promise<void>;
  signInWithSSO: () => Promise<void>;
  signUp: () => void;
  signOut: () => Promise<void>;
  resetPassword: () => void;
  openAccountConsole: () => void;
  loading: boolean;
  hasHunrenAccess: boolean;
  isAdmin: boolean;
  refreshPermissions: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const oidc = useOidcAuth();
  const [hasHunrenAccess, setHasHunrenAccess] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const tokenGetterSet = useRef(false);

  // Derive user from OIDC profile
  const user: AuthUser | null = oidc.user
    ? {
        id: oidc.user.profile.sub,
        email: (oidc.user.profile.email as string) ?? '',
        name: (oidc.user.profile.name as string) ?? undefined,
        givenName: (oidc.user.profile.given_name as string) ?? undefined,
        familyName: (oidc.user.profile.family_name as string) ?? undefined,
      }
    : null;

  const loading = oidc.isLoading;

  // Set up token getter for api.ts and sseService.ts
  useEffect(() => {
    if (!tokenGetterSet.current) {
      setTokenGetter(() => oidc.user?.access_token ?? null);
      tokenGetterSet.current = true;
    }
  }, [oidc.user]);

  // Update the token getter whenever the oidc user changes (token refresh)
  useEffect(() => {
    setTokenGetter(() => oidc.user?.access_token ?? null);
  }, [oidc.user]);

  // Set up 401 handler to trigger OIDC re-authentication
  useEffect(() => {
    setSignOutHandler(() => {
      oidc.signinRedirect();
    });
  }, [oidc]);

  // Fetch permissions from backend
  const fetchPermissions = useCallback(async () => {
    try {
      const response = await permissionsService.getMyPermissions();
      setHasHunrenAccess(response.data.use_hunren_keys);
      setIsAdmin(response.data.is_admin);
    } catch {
      setHasHunrenAccess(false);
      setIsAdmin(false);
    }
  }, []);

  const refreshPermissions = useCallback(async () => {
    if (user) {
      await fetchPermissions();
    }
  }, [user, fetchPermissions]);

  // Fetch permissions when user changes
  useEffect(() => {
    if (user) {
      fetchPermissions();
    } else {
      setHasHunrenAccess(false);
      setIsAdmin(false);
    }
  }, [user?.id, fetchPermissions]);

  const signingIn = useRef(false);
  const signIn = useCallback(async () => {
    if (signingIn.current) return;
    signingIn.current = true;
    await oidc.signinRedirect();
  }, [oidc]);

  const signInWithSSO = async () => {
    await oidc.signinRedirect({
      extraQueryParams: { kc_idp_hint: 'microsoft' },
    });
  };

  const signUp = () => {
    const settings = oidc.settings;
    const authority = settings.authority;
    const clientId = settings.client_id;
    const redirectUri = settings.redirect_uri;
    window.location.href =
      `${authority}/protocol/openid-connect/registrations` +
      `?client_id=${encodeURIComponent(clientId)}` +
      `&redirect_uri=${encodeURIComponent(redirectUri)}` +
      `&response_type=code` +
      `&scope=openid email profile`;
  };

  const signOut = async () => {
    await oidc.signoutRedirect({
      post_logout_redirect_uri: window.location.origin + '/',
    });
  };

  const resetPassword = () => {
    const { authority, client_id, redirect_uri } = oidc.settings;
    window.location.href =
      `${authority}/login-actions/reset-credentials` +
      `?client_id=${encodeURIComponent(client_id)}` +
      `&redirect_uri=${encodeURIComponent(redirect_uri)}`;
  };

  const openAccountConsole = () => {
    const { authority } = oidc.settings;
    window.open(`${authority}/account`, '_blank');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        signIn,
        signInWithSSO,
        signUp,
        signOut,
        resetPassword,
        openAccountConsole,
        loading,
        hasHunrenAccess,
        isAdmin,
        refreshPermissions,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
