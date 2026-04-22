import { type ButtonHTMLAttributes } from 'react'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger' | 'secondary'
  size?: 'sm' | 'md' | 'lg'
}

const variants = {
  primary: 'bg-violet-600 hover:bg-violet-500 text-white border-transparent',
  secondary: 'bg-slate-700 hover:bg-slate-600 text-slate-200 border-slate-600',
  ghost: 'bg-transparent hover:bg-slate-700/60 text-slate-300 border-transparent',
  danger: 'bg-red-700/80 hover:bg-red-600 text-white border-transparent',
}

const sizes = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-4 py-1.5 text-sm',
  lg: 'px-6 py-2.5 text-base',
}

export function Button({ variant = 'secondary', size = 'md', className = '', children, ...props }: Props) {
  return (
    <button
      className={`inline-flex items-center gap-1.5 rounded border font-medium transition-colors
        disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer
        ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
