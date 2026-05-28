import { useState, useEffect, useRef, useCallback } from 'react'
import { Plane, Camera, Video, VideoOff, AlertOctagon, Eye, EyeOff, Cpu } from 'lucide-react'
import VirtualJoystick from '../components/VirtualJoystick'

export default function Dashboard({ telemetry }) {
  const [recording, setRecording] = useState(false)
  const [recDuration, setRecDuration] = useState(0)
  const [cameraDir, setCameraDir] = useState(0)
  const [isMobile, setIsMobile] = useState(false)
  const [feedError, setFeedError] = useState(false)
  const [yoloEnabled, setYoloEnabled] = useState(false)
  const keysRef = useRef({})
  const rcInterval = useRef(null)
  const joystickRC = useRef({ lr: 0, fb: 0, ud: 0, yv: 0 })

  const post = async (endpoint, body = {}) => {
    try {
      const res = await fetch(`/api/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      return await res.json()
    } catch (e) { console.error(e) }
  }

  const handleTakeoff = () => post('takeoff')
  const handleLand = () => post('land')
  const handleEmergency = () => { if (confirm('EMERGENCY STOP — Kill all motors immediately?')) post('emergency') }
  const handleFlip = (dir) => post('flip', { direction: dir })
  const handleCamera = () => {
    const next = cameraDir === 0 ? 1 : 0
    post('camera', { direction: next })
    setCameraDir(next)
  }
  const handleAutopilot = () => post('autopilot/toggle')

  const toggleRecording = async () => {
    if (recording) {
      await post('recorder/stop')
      setRecording(false)
      setRecDuration(0)
    } else {
      await post('recorder/start')
      setRecording(true)
    }
  }

  useEffect(() => {
    if (!recording) return
    const t = setInterval(() => setRecDuration(d => d + 1), 1000)
    return () => clearInterval(t)
  }, [recording])

  useEffect(() => {
    const timer = setTimeout(() => {
      setFeedError(false)
    }, 0)
    return () => clearTimeout(timer)
  }, [telemetry.connected])

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

  const toggleYolo = async () => {
    const next = !yoloEnabled
    setYoloEnabled(next)
    try {
      await fetch('/api/settings/yolo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      })
    } catch (err) {
      console.error(err)
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchYoloConfig()
    }, 0)
    return () => clearTimeout(timer)
  }, [])

  // Detect touch device
  useEffect(() => {
    const check = () => setIsMobile('ontouchstart' in window || navigator.maxTouchPoints > 0)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  // Joystick handlers for mobile
  const handleLeftStick = useCallback((x, y) => {
    const speed = 60
    joystickRC.current.lr = Math.round(x * speed)
    joystickRC.current.fb = Math.round(y * speed)
  }, [])

  const handleRightStick = useCallback((x, y) => {
    const speed = 60
    joystickRC.current.yv = Math.round(x * speed)
    joystickRC.current.ud = Math.round(y * speed)
  }, [])

  // Unified RC send loop (keyboard + joystick)
  useEffect(() => {
    const handleDown = (e) => { keysRef.current[e.key.toLowerCase()] = true }
    const handleUp = (e) => { keysRef.current[e.key.toLowerCase()] = false }
    window.addEventListener('keydown', handleDown)
    window.addEventListener('keyup', handleUp)

    const lastRC = { lr: 0, fb: 0, ud: 0, yv: 0 }
    rcInterval.current = setInterval(() => {
      const k = keysRef.current
      const speed = 60
      const kbLr = (k['d'] ? speed : 0) - (k['a'] ? speed : 0)
      const kbFb = (k['w'] ? speed : 0) - (k['s'] ? speed : 0)
      const kbUd = (k['arrowup'] ? speed : 0) - (k['arrowdown'] ? speed : 0)
      const kbYv = (k['arrowright'] ? speed : 0) - (k['arrowleft'] ? speed : 0)
      const j = joystickRC.current
      const lr = kbLr || j.lr
      const fb = kbFb || j.fb
      const ud = kbUd || j.ud
      const yv = kbYv || j.yv
      
      const anyActive = lr || fb || ud || yv
      const wasActive = lastRC.lr || lastRC.fb || lastRC.ud || lastRC.yv
      if (anyActive || wasActive) {
        lastRC.lr = lr; lastRC.fb = fb; lastRC.ud = ud; lastRC.yv = yv
        fetch('/api/rc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lr, fb, ud, yv }) }).catch(() => {})
      }
    }, 50)

    return () => {
      window.removeEventListener('keydown', handleDown)
      window.removeEventListener('keyup', handleUp)
      clearInterval(rcInterval.current)
    }
  }, [])

  const formatTime = (s) => `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`

  const showFeed = telemetry.connected && !feedError

  if (isMobile) {
    return (
      <div className="h-full flex flex-col bg-[#090a0c] text-white p-4">
        {/* Mobile Video Feed */}
        <div className="flex-1 relative rounded-xl border border-white/5 bg-[#121316] overflow-hidden shadow-inner flex items-center justify-center">
          {showFeed ? (
            <img
              src="/api/video"
              alt="Drone Feed"
              className="w-full h-full object-cover"
              onError={() => setFeedError(true)}
            />
          ) : (
            <div className="text-center p-4">
              <Plane size={20} className="text-neutral-600 mx-auto mb-2" />
              <p className="text-xs text-neutral-500 font-medium">Link Offline</p>
            </div>
          )}
          
          <div className="absolute top-2 inset-x-2 flex justify-between text-[10px] font-mono bg-black/75 px-3 py-1.5 rounded-lg border border-white/5">
            <span>ALT: {telemetry.height}cm</span>
            <span>BAT: {telemetry.battery}%</span>
          </div>
        </div>

        {/* Flips Row */}
        <div className="my-3 flex justify-center gap-1.5">
          {['l','r','f','b'].map(dir => (
            <button
              key={dir}
              onClick={() => handleFlip(dir)}
              disabled={!telemetry.flying}
              className="pointer-events-auto px-3 py-1.5 rounded-lg bg-white/5 text-[9px] font-bold uppercase tracking-wider border border-white/5 disabled:opacity-20 transition-all active:scale-95"
            >
              {dir === 'l' ? 'Left' : dir === 'r' ? 'Right' : dir === 'f' ? 'Forward' : 'Backward'} Flip
            </button>
          ))}
        </div>

        {/* Mobile Takeoff Control */}
        <div className="flex justify-between items-center gap-3 py-1">
          <button
            onClick={telemetry.flying ? handleLand : handleTakeoff}
            disabled={!telemetry.connected}
            className={`flex-1 py-3 rounded-lg text-slate-950 font-bold text-xs uppercase tracking-wider transition-all ${
              telemetry.flying ? 'bg-warning' : 'bg-primary'
            } disabled:opacity-20`}
          >
            {telemetry.flying ? 'Land' : 'Takeoff'}
          </button>
        </div>

        {/* Joysticks */}
        <div className="flex justify-between items-center py-4 px-2">
          <VirtualJoystick onMove={handleLeftStick} label="Translation" size={100} />
          <VirtualJoystick onMove={handleRightStick} label="Heading/Alt" size={100} />
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex bg-[#090a0c] text-white">
      {/* LEFT COLUMN: Actions & Status */}
      <div className="w-64 border-r border-white/5 p-5 flex flex-col gap-6 shrink-0 bg-[#0c0d0f]/50">
        <div>
          <h3 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest mb-3">System Link</h3>
          <StatusBadge connected={telemetry.connected} flying={telemetry.flying} />
          {telemetry.drone_name && (
            <div className="mt-2.5 text-xs text-neutral-400 font-semibold font-mono">
              IP: <span className="text-white">{telemetry.ip}</span>
            </div>
          )}
        </div>
        
        <div className="space-y-3">
          <h3 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest">Flight Tricks</h3>
          <div className="flex flex-col gap-1.5">
            <FlipBtn label="Flip Left" onClick={() => handleFlip('l')} disabled={!telemetry.flying} />
            <FlipBtn label="Flip Right" onClick={() => handleFlip('r')} disabled={!telemetry.flying} />
            <FlipBtn label="Flip Forward" onClick={() => handleFlip('f')} disabled={!telemetry.flying} />
            <FlipBtn label="Flip Backward" onClick={() => handleFlip('b')} disabled={!telemetry.flying} />
          </div>
        </div>

        <div className="mt-auto space-y-2 border-t border-white/5 pt-4">
          <h3 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest">Keyboard Control</h3>
          <div className="text-[11px] text-neutral-400 space-y-1.5 font-mono leading-relaxed">
            <div className="flex justify-between"><span className="text-neutral-500">WASD</span> <span>Pitch/Roll</span></div>
            <div className="flex justify-between"><span className="text-neutral-500">Arrows</span> <span>Yaw/Throttle</span></div>
          </div>
        </div>
      </div>

      {/* CENTER COLUMN: Live Video Viewport */}
      <div className="flex-1 flex flex-col p-6 min-w-0">
        <div className="flex-1 relative rounded-2xl border border-white/5 bg-[#111215] overflow-hidden shadow-2xl flex items-center justify-center group">
          {/* Feed or Neutral Standby Screen */}
          {showFeed ? (
            <img
              src="/api/video"
              alt="Drone Feed"
              className="w-full h-full object-cover"
              onError={() => setFeedError(true)}
            />
          ) : (
            <div className="flex flex-col items-center justify-center text-center p-8 max-w-xs">
              <Plane size={24} className="text-neutral-700 mb-3" />
              <h4 className="text-xs font-bold text-neutral-300 uppercase tracking-wider mb-1.5">Awaiting Link Stream</h4>
              <p className="text-xs text-neutral-500 leading-relaxed">
                Start the backend server and verify your connection in Settings to initialize video telemetry.
              </p>
            </div>
          )}

          {/* Minimal Grey Center Point */}
          {showFeed && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-25">
              <div className="w-6 h-6 border border-white rounded-full flex items-center justify-center">
                <div className="w-1 h-1 bg-white rounded-full" />
              </div>
            </div>
          )}

          {/* Clean HUD Strip at Top of Viewport */}
          <div className="absolute top-0 inset-x-0 bg-gradient-to-b from-black/85 to-transparent px-5 py-4 flex justify-between items-center text-[11px] font-mono text-neutral-300 tracking-wide select-none">
            <div className="flex items-center gap-4">
              <span>ALT: <b className="text-white">{telemetry.height} cm</b></span>
              <span className="text-neutral-600">|</span>
              <span>SPD: <b className="text-white">{telemetry.speed} c/s</b></span>
            </div>
            <div className="flex items-center gap-4">
              <span>BAT: <b className={telemetry.battery > 20 ? 'text-success font-bold' : 'text-danger font-bold'}>{telemetry.battery}%</b></span>
              <span className="text-neutral-600">|</span>
              <span>TEMP: <b className="text-white">{telemetry.temperature}°C</b></span>
            </div>
          </div>
        </div>

        {/* Action Controls Panel below Viewport */}
        <div className="mt-5 flex items-center justify-center gap-2">
          {/* Record button */}
          <div className={`flex items-center rounded-xl border transition-all ${
            recording 
              ? 'bg-danger/10 border-danger/25 px-3 py-1 gap-2' 
              : 'bg-white/5 border-white/5 p-1'
          }`}>
            <button
              onClick={toggleRecording}
              disabled={!telemetry.connected}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer ${
                recording
                  ? 'text-danger'
                  : 'text-neutral-400 hover:text-white'
              } disabled:opacity-25`}
              title={recording ? 'Stop Recording' : 'Start Recording'}
            >
              {recording ? <VideoOff size={14} /> : <Video size={14} />}
            </button>
            {recording && (
              <span className="text-[10px] text-danger font-mono font-bold tracking-wider animate-pulse select-none">
                {formatTime(recDuration)}
              </span>
            )}
          </div>

          {/* Toggle Camera direction */}
          <button
            onClick={handleCamera}
            disabled={!telemetry.connected}
            className="w-10 h-10 rounded-xl bg-white/5 border border-white/5 text-neutral-400 hover:text-white hover:bg-white/10 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-20"
            title="Toggle View Mode"
          >
            <Camera size={14} />
          </button>

          {/* Toggle YOLO Overlay */}
          <button
            onClick={toggleYolo}
            className={`w-10 h-10 rounded-xl border flex items-center justify-center transition-colors cursor-pointer ${
              yoloEnabled
                ? 'bg-white text-slate-950 border-white'
                : 'bg-white/5 border-white/5 text-neutral-400 hover:text-white hover:bg-white/10'
            }`}
            title="Toggle YOLO Vision Overlay"
          >
            {yoloEnabled ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>

          {/* Autopilot Button */}
          <button
            onClick={handleAutopilot}
            disabled={!telemetry.connected}
            className={`px-5 h-10 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 cursor-pointer flex items-center gap-2 border ${
              telemetry.autopilot_active
                ? 'bg-gradient-to-r from-indigo-600 to-violet-600 border-indigo-500 text-white shadow-[0_0_15px_rgba(99,102,241,0.4)]'
                : 'bg-white/5 border-white/5 text-neutral-400 hover:text-white hover:bg-white/10 hover:border-white/10'
            } disabled:opacity-20`}
            title="Toggle Autopilot Flight Loop"
          >
            <Cpu size={14} className={telemetry.autopilot_active ? 'animate-spin' : ''} style={{ animationDuration: '3s' }} />
            <span>
              {telemetry.autopilot_active 
                ? `AP: ${telemetry.autopilot_phase}`
                : 'Autopilot'}
            </span>
          </button>

          {/* Core Takeoff action */}
          <button
            onClick={telemetry.flying ? handleLand : handleTakeoff}
            disabled={!telemetry.connected}
            className={`px-8 h-10 rounded-xl text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer ${
              telemetry.flying
                ? 'bg-warning hover:bg-amber-400 text-slate-950 shadow-sm'
                : 'bg-primary hover:bg-sky-400 text-slate-950 shadow-sm'
            } disabled:opacity-20`}
          >
            {telemetry.flying ? 'Land Flight' : 'Takeoff Flight'}
          </button>

          {/* Emergency Stop */}
          <button
            onClick={handleEmergency}
            disabled={!telemetry.connected}
            className="w-10 h-10 rounded-xl bg-danger/10 border border-danger/15 text-danger hover:bg-danger/20 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-20"
            title="EMERGENCY STOP (WIPE ENGINES)"
          >
            <AlertOctagon size={14} />
          </button>
        </div>
      </div>

      {/* RIGHT COLUMN: Real-Time Telemetry Dials */}
      <div className="w-64 border-l border-white/5 p-5 flex flex-col gap-5 shrink-0 bg-[#0c0d0f]/50">
        <h3 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest">Telemetry Metrics</h3>
        <div className="flex flex-col gap-4">
          <StatBox label="Sensor Altitude" value={`${telemetry.height}`} unit="cm" />
          <StatBox label="Horizontal Speed" value={`${telemetry.speed}`} unit="cm/s" />
          
          <div className="grid grid-cols-3 gap-2">
            <MiniStatBox label="Yaw" value={`${telemetry.yaw}°`} />
            <MiniStatBox label="Pitch" value={`${telemetry.pitch}°`} />
            <MiniStatBox label="Roll" value={`${telemetry.roll}°`} />
          </div>

          <StatBox label="Active flight duration" value={formatTime(Math.round(telemetry.flight_duration || 0))} />
          <StatBox label="Estimated Distance" value={`${Math.round(telemetry.total_distance || 0)}`} unit="cm" />
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ connected, flying }) {
  if (!connected) return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-neutral-900 border border-white/5 text-neutral-500 text-xs font-semibold">
      <span className="w-1.5 h-1.5 rounded-full bg-neutral-700" />
      Standby
    </div>
  )
  if (flying) return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs font-semibold">
      <span className="w-1.5 h-1.5 rounded-full bg-primary" />
      Active Flight
    </div>
  )
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-success/10 border border-success/20 text-success text-xs font-semibold">
      <span className="w-1.5 h-1.5 rounded-full bg-success" />
      Telemetry Ready
    </div>
  )
}

function FlipBtn({ label, onClick, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 text-xs text-neutral-300 hover:text-white font-medium text-left transition-colors cursor-pointer disabled:opacity-20 disabled:pointer-events-none"
    >
      {label}
    </button>
  )
}

function StatBox({ label, value, unit }) {
  return (
    <div className="p-3.5 rounded-xl border border-white/5 bg-[#121316]">
      <span className="text-[10px] text-neutral-500 uppercase tracking-wider font-semibold block mb-1">{label}</span>
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-bold font-mono tracking-tight text-white">{value}</span>
        {unit && <span className="text-xs text-neutral-500 font-medium">{unit}</span>}
      </div>
    </div>
  )
}

function MiniStatBox({ label, value }) {
  return (
    <div className="p-2.5 rounded-lg border border-white/5 bg-[#121316] text-center">
      <span className="text-[9px] text-neutral-500 uppercase block font-semibold mb-0.5">{label}</span>
      <span className="text-[11px] font-bold font-mono text-white">{value}</span>
    </div>
  )
}
