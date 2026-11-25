import React from 'react';

interface UserAvatarProps {
  email?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeClasses = {
  sm: 'w-8 h-8 text-xs',
  md: 'w-10 h-10 text-sm',
  lg: 'w-14 h-14 text-lg',
};

export const UserAvatar: React.FC<UserAvatarProps> = ({ email, size = 'md', className = '' }) => {
  const initials = email
    ? email
        .split('@')[0]
        .split(/[._-]/)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase() || '')
        .join('')
    : '?';

  return (
    <div
      className={`rounded-full bg-brand-500 text-white flex items-center justify-center font-semibold select-none flex-shrink-0 ${sizeClasses[size]} ${className}`}
    >
      {initials}
    </div>
  );
};

export default UserAvatar;
