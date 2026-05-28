import { useRef, useCallback, useEffect, useState } from 'react'

export default function VirtualJoystick({ onMove, label, size = 120 }) {
  const containerRef = useRef(null)
  const [active, setActive] = useState(false)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const touchIdRef = useRef(null)

  const radius = size / 2 - 16
  const knobSize = size * 0.35

  const getRelativePos = useCallback((clientX, clientY) => {
    const rect = containerRef.current.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    let dx = clientX - cx
    let dy = clientY - cy
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist > radius) {
      dx = (dx / dist) * radius
      dy = (dy / dist) * radius
    }
    return { x: dx / radius, y: -dy / radius }
  }, [radius])

  const handleStart = useCallback((e) => {
    e.preventDefault()
    const touch = e.changedTouches[0]
    touchIdRef.current = touch.identifier
    setActive(true)
    const p = getRelativePos(touch.clientX, touch.clientY)
    setPos(p)
    onMove(p.x, p.y)
  }, [getRelativePos, onMove])

  const handleMove = useCallback((e) => {
    e.preventDefault()
    for (const touch of e.changedTouches) {
      if (touch.identifier === touchIdRef.current) {
        const p = getRelativePos(touch.clientX, touch.clientY)
        setPos(p)
        onMove(p.x, p.y)
        break
      }
    }
  }, [getRelativePos, onMove])

  const handleEnd = useCallback((e) => {
    for (const touch of e.changedTouches) {
      if (touch.identifier === touchIdRef.current) {
        touchIdRef.current = null
        setActive(false)
        setPos({ x: 0, y: 0 })
        onMove(0, 0)
        break
      }
    }
  }, [onMove])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.addEventListener('touchstart', handleStart, { passive: false })
    el.addEventListener('touchmove', handleMove, { passive: false })
    el.addEventListener('touchend', handleEnd)
    el.addEventListener('touchcancel', handleEnd)
    return () => {
      el.removeEventListener('touchstart', handleStart)
      el.removeEventListener('touchmove', handleMove)
      el.removeEventListener('touchend', handleEnd)
      el.removeEventListener('touchcancel', handleEnd)
    }
  }, [handleStart, handleMove, handleEnd])

  const knobX = pos.x * radius
  const knobY = -pos.y * radius

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        ref={containerRef}
        className="relative rounded-full border border-white/10 bg-[#0d0e11] touch-none"
        style={{ width: size, height: size }}
      >
        {/* Crosshair lines */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="absolute w-px h-full bg-white/5" />
          <div className="absolute h-px w-full bg-white/5" />
        </div>
        {/* Knob */}
        <div
          className={`absolute rounded-full transition-transform border ${
            active 
              ? 'bg-white border-white' 
              : 'bg-white/10 border-white/5 hover:bg-white/20'
          }`}
          style={{
            width: knobSize,
            height: knobSize,
            left: '50%',
            top: '50%',
            transform: `translate(calc(-50% + ${knobX}px), calc(-50% + ${knobY}px))`,
            transition: active ? 'none' : 'transform 0.15s ease-out',
          }}
        />
      </div>
      <span className="text-[9px] text-neutral-500 font-bold uppercase tracking-wider">{label}</span>
    </div>
  )
}
