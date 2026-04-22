interface Props {
  children: React.ReactNode
  color?: string
  className?: string
}

export function Badge({ children, color, className = '' }: Props) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold ${className}`}
      style={color ? { background: color + '33', color } : undefined}
    >
      {children}
    </span>
  )
}
