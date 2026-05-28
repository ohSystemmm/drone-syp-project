import { useState, useEffect } from 'react'
import { Wifi, Play, Settings, ShieldAlert, Eye } from 'lucide-react'

export default function SettingsPage({ telemetry }) {
  const [droneIp, setDroneIp] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState('')
  const [recordings, setRecordings] = useState([])
  const [maxAlt, setMaxAlt] = useState(15)
  const [maxDist, setMaxDist] = useState(60)
  const [sensitivity, setSensitivity] = useState(75)
  const [yoloEnabled, setYoloEnabled] = useState(false)

  const fetchRegistry = async () => {
    try {
      const res = await fetch('/api/registry')
      if (res.ok) {
        const data = await res.json()
        if (data.last_active_ip) {
          setDroneIp(prev => prev || data.last_active_ip)
        }
      }
    } catch (err) {
      console.error(err)
    }
  }

  const fetchRecordings = async () => {
    try {
      const res = await fetch('/api/recorder/list')
      if (res.ok) setRecordings(await res.json())
    } catch (err) {
      console.error(err)
    }
  }

  const fetchYoloConfig = async () => {
    try {
      const res = await fetch('/api/settings/yolo')
      if (res.ok) {
        const data = await res.json()
        setYoloEnabled(data.enabled)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const toggleYolo = async (enabled) => {
    setYoloEnabled(enabled)
    try {
      await fetch('/api/settings/yolo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
    } catch (err) {
      console.error(err)
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchRegistry()
      fetchRecordings()
      fetchYoloConfig()
    }, 0)
    return () => clearTimeout(timer)
  }, [])

  const connect = async () => {
    if (!droneIp) return
    setConnecting(true)
    setError('')
    try {
      const res = await fetch('/api/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ip: droneIp }) })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || `Connection failed (${res.status})`)
      } else {
        await fetchRegistry()
      }
    } catch (err) {
      console.error(err)
      setError('Server unreachable — is the backend running on port 8000?')
    }
    setConnecting(false)
  }

  const disconnect = async () => {
    setError('')
    try {
      const res = await fetch('/api/disconnect', { method: 'POST' })
      if (!res.ok) setError('Disconnect failed')
    } catch (err) {
      console.error(err)
      setError('Server unreachable')
    }
  }



  const startReplay = async (path) => {
    await fetch('/api/recorder/replay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) })
  }

  const stopReplay = async () => {
    await fetch('/api/recorder/replay/stop', { method: 'POST' })
  }



  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6 pb-24">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-white">System Settings</h1>
        <p className="text-xs text-neutral-500 mt-1">Configure flight link networks, geofences, and calibrations</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Connection */}
        <Section title="Drone Connection" icon={<Wifi size={13} />}>
          <div className="space-y-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={droneIp}
                onChange={(e) => setDroneIp(e.target.value)}
                placeholder="192.168.x.x"
                className="flex-1 px-3 py-2 rounded-lg glass-input text-xs text-white focus:outline-none placeholder:text-neutral-700"
              />
              {telemetry.connected ? (
                <button
                  onClick={disconnect}
                  className="px-4 py-2 rounded-lg bg-danger/10 border border-danger/15 hover:bg-danger/25 text-danger text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer shrink-0"
                >
                  Disconnect
                </button>
              ) : (
                <button
                  onClick={connect}
                  disabled={connecting}
                  className="px-4 py-2 rounded-lg bg-white text-slate-950 hover:bg-neutral-200 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer disabled:opacity-20 shrink-0"
                >
                  {connecting ? 'Linking...' : 'Connect'}
                </button>
              )}
            </div>
            
            <div className="flex items-center gap-2 p-3 rounded-lg bg-[#0d0e11] border border-white/5 text-[11px] text-neutral-500">
              {telemetry.connected ? (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-success" />
                  <span>Connection Active &bull; <span className="text-white font-semibold font-mono">{telemetry.ip}</span></span>
                </>
              ) : (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-neutral-700" />
                  <span>Drone telemetry offline</span>
                </>
              )}
            </div>

            {error && (
              <div className="px-3 py-2 rounded-lg bg-danger/10 border border-danger/15 text-xs text-danger leading-relaxed">
                {error}
              </div>
            )}
          </div>
        </Section>


        {/* Flight limits */}
        <Section title="Safety Geofences" icon={<ShieldAlert size={13} />}>
          <div className="space-y-4">
            <Slider label="Max Altitude Limit" value={maxAlt} onChange={setMaxAlt} min={2} max={30} unit="m" />
            <Slider label="Max Geofence Range" value={maxDist} onChange={setMaxDist} min={10} max={100} unit="m" />
          </div>
        </Section>

        {/* Joystick Config */}
        <Section title="Joystick Settings" icon={<Settings size={13} />}>
          <Slider label="Control Sensitivity" value={sensitivity} onChange={setSensitivity} min={10} max={100} unit="%" />
        </Section>

        {/* Flight Recordings */}
        <Section title="Flight Logs" icon={<Play size={13} />}>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[9px] text-neutral-500 font-bold uppercase tracking-wider">{recordings.length} logs stored</p>
              <button onClick={stopReplay} className="text-[9px] font-bold uppercase px-2 py-1 rounded bg-white/5 border border-white/5 hover:bg-white/10 text-neutral-400 hover:text-white cursor-pointer">Stop Replay</button>
            </div>
            {recordings.length === 0 ? (
              <p className="text-xs text-neutral-600 py-6 text-center">No telemetry logs recorded on system disk.</p>
            ) : (
              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                {recordings.map((rec, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.01] border border-white/5 hover:border-white/10 transition-colors">
                    <Play size={10} className="text-neutral-500 shrink-0" />
                    <span className="flex-1 truncate text-[11px] font-medium text-neutral-300">{rec.name || rec.path || `Log Record ${i+1}`}</span>
                    <span className="text-[10px] text-neutral-500 font-mono shrink-0">{rec.duration ? `${Math.round(rec.duration)}s` : ''}</span>
                    <button
                      onClick={() => startReplay(rec.path)}
                      disabled={!telemetry.connected}
                      className="px-2.5 py-1 rounded-lg text-[9px] font-bold uppercase bg-white/5 border border-white/5 hover:bg-white/10 text-neutral-300 hover:text-white transition-colors cursor-pointer disabled:opacity-20 disabled:pointer-events-none"
                    >
                      Replay
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Section>

        {/* AI Vision Intelligence */}
        <Section title="AI Vision Control" icon={<Eye size={13} />}>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-3.5 rounded-xl border border-white/5 bg-[#121316]">
              <div>
                <p className="text-xs font-semibold text-neutral-200">YOLO Object Overlay</p>
                <p className="text-[10px] text-neutral-500 mt-0.5">Render real-time object tracking boxes on flight feed</p>
              </div>
              <button
                onClick={() => toggleYolo(!yoloEnabled)}
                className={`px-3.5 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-colors cursor-pointer border ${
                  yoloEnabled
                    ? 'bg-white text-slate-950 border-white'
                    : 'bg-white/5 border-white/5 text-neutral-400 hover:text-white'
                }`}
              >
                {yoloEnabled ? 'Active' : 'Disabled'}
              </button>
            </div>
            <div className="p-3 rounded-lg bg-[#0d0e11] border border-white/5 text-[10px] text-neutral-500 leading-relaxed">
              Enabling YOLO model will run local frame inference. Ensure the model file targetModel.onnx is loaded in your assets folder.
            </div>
          </div>
        </Section>
      </div>

    </div>
  )
}

function Section({ title, children, icon }) {
  return (
    <div className="border border-white/5 bg-[#121316] rounded-xl p-5 space-y-4">
      <h2 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest flex items-center gap-1.5">
        {icon}
        <span>{title}</span>
      </h2>
      {children}
    </div>
  )
}

function Slider({ label, value, onChange, min, max, unit }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-center text-xs">
        <span className="text-neutral-400 font-medium">{label}</span>
        <span className="text-white font-bold font-mono">{value}<span className="text-[10px] text-neutral-500 ml-0.5">{unit}</span></span>
      </div>
      <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-white" />
    </div>
  )
}
