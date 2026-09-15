import { useState } from 'react'

interface Props {
  src: string | null | undefined
  alt: string
  size?: 'sm' | 'lg' | 'xl'
}

const PX = { sm: 20, lg: 30, xl: 56 }

export function Crest({ src, alt, size = 'sm' }: Props) {
  const [failed, setFailed] = useState(false)
  const px = PX[size]
  const cls = size === 'sm' ? 'crest' : `crest crest--${size}`

  if (!src || failed) {
    const initials = alt.replace(/[^A-Za-z ]/g, '').split(/\s+/).map((w) => w[0]).slice(0, 3).join('')
    return (
      <span
        className={`${cls} crest-fallback`}
        style={{ width: px, height: px, fontSize: Math.max(8, px * 0.33) }}
        aria-label={alt}
        title={alt}
      >
        {initials || '?'}
      </span>
    )
  }

  return (
    <img
      className={cls}
      src={src}
      alt={alt}
      title={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}
