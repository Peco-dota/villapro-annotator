export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24"
      className="animate-spin text-violet-400"
      fill="none" stroke="currentColor" strokeWidth={2.5}
    >
      <circle cx="12" cy="12" r="10" strokeOpacity={0.2} />
      <path d="M12 2a10 10 0 0 1 10 10" />
    </svg>
  )
}
