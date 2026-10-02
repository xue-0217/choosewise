export function KeyboardArt({ tone = 'cream', compact = false }: { tone?: string; compact?: boolean }) {
  const dark = tone === 'ink'
  const base = dark ? '#353b36' : tone === 'sage' ? '#c7d2bc' : '#d5d3cc'
  const key = dark ? '#50584f' : '#faf9f5'
  return <svg viewBox="0 0 460 215" role="img" aria-label="键盘结构示意图" className={compact ? 'device-keyboard compact' : 'device-keyboard'}>
    <rect x="12" y="16" width="435" height="183" rx="14" fill={base} />
    <rect x="18" y="20" width="424" height="171" rx="11" fill={dark ? '#252a26' : '#aaa99f'} />
    {Array.from({ length: 5 }, (_, row) => Array.from({ length: 14 }, (_, col) => {
      if (row === 4 && col > 2 && col < 9) return null
      return <g key={`${row}-${col}`}>
        <rect x={26 + col * 29} y={28 + row * 31} width="25" height="27" rx="4" fill={col === 13 || (row === 0 && col === 0) ? '#bdcda0' : key} />
        <rect x={29 + col * 29} y={30 + row * 31} width="19" height="21" rx="3" fill={col === 13 || (row === 0 && col === 0) ? '#d2dfb7' : dark ? '#576052' : '#fffef9'} />
        <path d={`M${32 + col * 29} ${35 + row * 31}h4`} stroke={dark ? '#aeb6a6' : '#aaa99d'} strokeWidth="1" />
      </g>
    }))}
    <rect x="113" y="152" width="170" height="27" rx="4" fill={key} />
    <path d="M130 166h134" stroke={dark ? '#727e68' : '#e6e4d9'} strokeWidth="1" />
    <circle cx="432" cy="187" r="2" fill="#7b8d60" />
  </svg>
}

export function MouseArt({ tone = 'cream' }: { tone?: string }) {
  const dark = tone === 'ink'
  return <svg viewBox="0 0 145 210" role="img" aria-label="鼠标结构示意图" className="device-mouse">
    <path d="M24 89C24 25 47 9 72 9s49 16 49 80v48c0 43-21 62-49 62s-48-19-48-62z" fill={dark ? '#383f35' : tone === 'sage' ? '#cbd7be' : '#e5e3db'} />
    <path d="M31 84c0-50 17-66 41-66s42 16 42 66" fill={dark ? '#515a49' : '#f6f5ed'} />
    <path d="M72 19v63M31 85h83" stroke={dark ? '#2c322a' : '#c7c6bd'} strokeWidth="1.8" />
    <rect x="66" y="42" width="12" height="29" rx="6" fill="#788665" />
    {[47, 52, 57, 62, 67].map(y => <path key={y} d={`M68 ${y}h8`} stroke="#b4c49e" />)}
    <path d="M38 160c5 20 18 28 34 28" fill="none" stroke={dark ? '#58624f' : '#f7f6ee'} strokeWidth="2" />
  </svg>
}
