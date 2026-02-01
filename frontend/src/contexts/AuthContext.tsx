import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { supabase } from '@services/supabaseClient';
import { permissionsService } from '@services/api';
import { User, Session } from '@supabase/supabase-js';

interface AuthContextType {
  user: User | null;
  session: Session | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  loading: boolean;
  hasHunrenAccess: boolean;
  isAdmin: boolean;
  refreshPermissions: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasHunrenAccess, setHasHunrenAccess] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  // Fetch permissions from backend
  const fetchPermissions = useCallback(async () => {
    try {
      const response = await permissionsService.getMyPermissions();
      setHasHunrenAccess(response.data.use_hunren_keys);
      setIsAdmin(response.data.is_admin);
    } catch (error) {
      // User not authenticated or error - default to no access
      setHasHunrenAccess(false);
      setIsAdmin(false);
    }
  }, []);

  // Allow manual refresh of permissions (e.g., after admin grants access)
  const refreshPermissions = useCallback(async () => {
    if (session) {
      await fetchPermissions();
    }
  }, [session, fetchPermissions]);

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    });

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setUser(session?.user ?? null);
    });

    return () => subscription.unsubscribe();
  }, []);

  // Fetch permissions when user changes
  useEffect(() => {
    if (user) {
      fetchPermissions();
    } else {
      setHasHunrenAccess(false);
      setIsAdmin(false);
    }
  }, [user, fetchPermissions]);

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) throw error;
  };

  const signUp = async (email: string, password: string) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
    });
    if (error) throw error;
  };

  const signOut = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  };

  const resetPassword = async (email: string) => {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: window.location.origin + '/reset-password', // We might need to handle this route later, or just let Supabase handle the email link
    });
    if (error) throw error;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        signIn,
        signUp,
        signOut,
        resetPassword,
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

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
