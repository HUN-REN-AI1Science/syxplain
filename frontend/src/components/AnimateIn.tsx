import React, { useEffect, useRef, useState } from 'react';

interface AnimateInProps {
  children: React.ReactNode;
  delay?: number;
  direction?: 'up' | 'down' | 'left' | 'right';
  className?: string;
}

const directionTransform = {
  up: 'translateY(16px)',
  down: 'translateY(-16px)',
  left: 'translateX(16px)',
  right: 'translateX(-16px)',
};

export const AnimateIn: React.FC<AnimateInProps> = ({
  children,
  delay = 0,
  direction = 'up',
  className = '',
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translate(0)' : directionTransform[direction],
        transition: `opacity var(--duration-slow) var(--ease-spring), transform var(--duration-slow) var(--ease-spring)`,
      }}
    >
      {children}
    </div>
  );
};

export default AnimateIn;
