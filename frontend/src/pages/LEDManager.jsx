import { useState } from 'react'
import { Sparkles, RotateCcw, Send, Settings2, Play } from 'lucide-react'

const COLORS = {
  '0': 'bg-slate-900 border border-white/5 hover:bg-slate-800',
  'r': 'bg-red-500 border border-red-400',
  'b': 'bg-blue-500 border border-blue-400',
  'p': 'bg-purple-500 border border-purple-400',
}

const COLOR_KEYS = ['0', 'r', 'b', 'p']
const COLOR_LABELS = { '0': 'Off', 'r': 'Red', 'b': 'Blue', 'p': 'Purple' }

const PRESETS = [
  {
    name: 'Smiley Face',
    pattern: [
      '00000000',
      '00r00r00',
      '00r00r00',
      '00000000',
      '0r0000r0',
      '00rrrr00',
      '00000000',
      '00000000',
    ].join(''),
  },
  {
    name: 'Heart Icon',
    pattern: [
      '00000000',
      '0rr0rr00',
      'rrrrrrr0',
      'rrrrrrr0',
      '0rrrrr00',
      '00rrr000',
      '000r0000',
      '00000000',
    ].join(''),
  },
  {
    name: 'Arrow Right',
    pattern: [
      '000r0000',
      '000rr000',
      '000rrr00',
      'rrrrrrrr',
      'rrrrrrrr',
      '000rrr00',
      '000rr000',
      '000r0000',
    ].join(''),
  },
  {
    name: 'X Mark',
    pattern: [
      'r000000r',
      '0r0000r0',
      '00r00r00',
      '000rr000',
      '000rr000',
      '00r00r00',
      '0r0000r0',
      'r000000r',
    ].join(''),
  },
]

export default function LEDManager() {
  const [grid, setGrid] = useState(Array(64).fill('0'))
  const [activeColor, setActiveColor] = useState('r')
  const [painting, setPainting] = useState(false)
  const [scrollText, setScrollText] = useState('')
  const [scrollColor, setScrollColor] = useState('r')
  const [scrollDir, setScrollDir] = useState('l')
  const [scrollSpeed, setScrollSpeed] = useState(1.0)
  const [status, setStatus] = useState('')

  const toggleCell = (i) => {
    const next = [...grid]
    next[i] = grid[i] === '0' ? activeColor : '0'
    setGrid(next)
  }

  const paintCell = (i) => {
    if (!painting) return
    const next = [...grid]
    next[i] = activeColor
    setGrid(next)
  }

  const applyPattern = async () => {
    const pattern = grid.join('')
    setStatus('Sending...')
    try {
      const res = await fetch('/api/led/pattern', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pattern }),
      })
      const data = await res.json()
      setStatus(data.status === 'success' ? 'Applied!' : data.detail || 'Error')
    } catch {
      setStatus('Connection error')
    }
    setTimeout(() => setStatus(''), 2000)
  }

  const sendText = async () => {
    if (!scrollText) return
    setStatus('Sending text...')
    try {
      const res = await fetch('/api/led/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: scrollText, color: scrollColor, direction: scrollDir, speed: scrollSpeed }),
      })
      const data = await res.json()
      setStatus(data.status === 'success' ? 'Scrolling!' : data.detail || 'Error')
    } catch {
      setStatus('Connection error')
    }
    setTimeout(() => setStatus(''), 2000)
  }

  const loadPreset = (preset) => setGrid(preset.pattern.split(''))
  const clearGrid = () => setGrid(Array(64).fill('0'))
  const clearDrone = async () => {
    setStatus('Clearing...')
    try {
      const res = await fetch('/api/led/clear', { method: 'POST' })
      const data = await res.json()
      setStatus(data.status === 'success' ? 'Cleared!' : data.detail || 'Error')
    } catch { setStatus('Connection error') }
    setTimeout(() => setStatus(''), 2000)
    setGrid(Array(64).fill('0'))
  }

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-6">
      {/* Header section */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white">LED Panel Manager</h1>
          <p className="text-xs text-neutral-500 mt-1">Configure LED matrix drawings and text overlays</p>
        </div>
        {status && (
          <span className="text-xs px-3.5 py-1.5 rounded-lg bg-white/5 border border-white/10 text-neutral-300 font-semibold font-mono">
            {status}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LED Matrix Grid Configuration */}
        <div className="lg:col-span-7 border border-white/5 bg-[#121316] rounded-xl p-5 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider flex items-center gap-1.5">
              <Sparkles size={13} /> LED Grid Canvas
            </h2>
            <button onClick={clearGrid} className="text-[11px] text-neutral-500 hover:text-white transition-colors flex items-center gap-1 cursor-pointer">
              <RotateCcw size={12} /> Clear Board
            </button>
          </div>

          <div
            className="grid grid-cols-8 gap-1.5 p-3 rounded-lg bg-[#0d0e11] border border-white/5"
            onMouseLeave={() => setPainting(false)}
          >
            {grid.map((cell, i) => (
              <button
                key={i}
                className={`aspect-square rounded ${COLORS[cell]} transition-all cursor-crosshair`}
                onMouseDown={() => { setPainting(true); toggleCell(i) }}
                onMouseEnter={() => paintCell(i)}
                onMouseUp={() => setPainting(false)}
              />
            ))}
          </div>

          {/* Color Picker */}
          <div className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.01] border border-white/5">
            <span className="text-xs text-neutral-500 font-medium">Draw Color:</span>
            <div className="flex items-center gap-2">
              {COLOR_KEYS.map((c) => (
                <button
                  key={c}
                  onClick={() => setActiveColor(c)}
                  className={`w-6 h-6 rounded border transition-all cursor-pointer ${c === '0'
                    ? 'bg-slate-800 border-white/10'
                    : c === 'r'
                      ? 'bg-red-500 border-red-400'
                      : c === 'b'
                        ? 'bg-blue-500 border-blue-400'
                        : 'bg-purple-500 border-purple-400'
                    } ${activeColor === c
                      ? 'ring-2 ring-primary ring-offset-2 ring-offset-[#121316] scale-105'
                      : 'opacity-70 hover:opacity-100'
                    }`}
                  title={COLOR_LABELS[c]}
                />
              ))}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex gap-2">
            <button
              onClick={applyPattern}
              className="flex-1 py-2.5 rounded-lg bg-primary hover:bg-sky-400 text-slate-950 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer"
            >
              Apply to Drone
            </button>
            <button
              onClick={clearDrone}
              className="px-4 py-2.5 rounded-lg bg-danger/10 border border-danger/15 hover:bg-danger/20 text-danger text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer"
            >
              Clear Panel
            </button>
          </div>
        </div>

        {/* Presets and Scrolling Text Panel */}
        <div className="lg:col-span-5 space-y-6">
          {/* Quick Presets */}
          <div className="border border-white/5 bg-[#121316] rounded-xl p-5 space-y-4">
            <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider flex items-center gap-1.5">
              <Settings2 size={13} /> Grid Presets
            </h2>
            <div className="grid grid-cols-2 gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p.name}
                  onClick={() => loadPreset(p)}
                  className="py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 text-xs text-neutral-300 hover:text-white font-medium transition-colors text-left flex items-center justify-between cursor-pointer"
                >
                  <span>{p.name}</span>
                  <Play size={10} className="text-neutral-600" />
                </button>
              ))}
            </div>
          </div>

          {/* Scrolling HUD Text */}
          <div className="border border-white/5 bg-[#121316] rounded-xl p-5 space-y-4">
            <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider flex items-center gap-1.5">
              <Send size={13} /> Text Scroller
            </h2>
            <div className="space-y-3">
              <div>
                <input
                  type="text"
                  value={scrollText}
                  onChange={(e) => setScrollText(e.target.value)}
                  placeholder="Enter message..."
                  className="w-full px-3 py-2 rounded-lg glass-input text-white text-xs placeholder:text-neutral-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[9px] text-neutral-500 font-bold block mb-1 uppercase tracking-wider">Direction</label>
                  <select
                    value={scrollDir}
                    onChange={(e) => setScrollDir(e.target.value)}
                    className="w-full px-2 py-1.5 rounded-lg glass-input text-xs text-white focus:outline-none"
                  >
                    <option value="l" className="bg-[#121316]">Left</option>
                    <option value="r" className="bg-[#121316]">Right</option>
                    <option value="u" className="bg-[#121316]">Up</option>
                    <option value="d" className="bg-[#121316]">Down</option>
                  </select>
                </div>
                <div>
                  <label className="text-[9px] text-neutral-500 font-bold block mb-1 uppercase tracking-wider">Color</label>
                  <select
                    value={scrollColor}
                    onChange={(e) => setScrollColor(e.target.value)}
                    className="w-full px-2 py-1.5 rounded-lg glass-input text-xs text-white focus:outline-none"
                  >
                    <option value="r" className="bg-[#121316]">Red</option>
                    <option value="b" className="bg-[#121316]">Blue</option>
                    <option value="p" className="bg-[#121316]">Purple</option>
                  </select>
                </div>
              </div>

              <div className="pt-2 border-t border-white/[0.03] space-y-1.5">
                <div className="flex justify-between items-center text-[10px] text-neutral-500 font-semibold uppercase">
                  <span>Scroll Speed</span>
                  <span className="text-white font-mono">{scrollSpeed.toFixed(1)}x</span>
                </div>
                <input
                  type="range"
                  min="0.1"
                  max="2.5"
                  step="0.1"
                  value={scrollSpeed}
                  onChange={(e) => setScrollSpeed(Number(e.target.value))}
                  className="w-full accent-primary"
                />
              </div>

              <button
                onClick={sendText}
                className="w-full py-2.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 text-xs text-white font-bold uppercase tracking-wider transition-colors cursor-pointer"
              >
                Send Text
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
