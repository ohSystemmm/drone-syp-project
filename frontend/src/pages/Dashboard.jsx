import { useState, useEffect, useRef, useCallback } from 'react'
import { Plane, Camera, SwitchCamera, Video, VideoOff, AlertOctagon, Eye, EyeOff, Cpu, Route, RouteOff } from 'lucide-react'
import VirtualJoystick from '../components/VirtualJoystick'

export default function Dashboard({ telemetry }) {
  const [pathRecording, setPathRecording] = useState(false)
  const [pathDuration, setPathDuration] = useState(0)
  const [videoRecording, setVideoRecording] = useState(false)
  const [videoDuration, setVideoDuration] = useState(0)
  const [photoFlash, setPhotoFlash] = useState(false)
  const [cameraDir, setCameraDir] = useState(0)
  const [isMobile, setIsMobile] = useState(false)
  const [feedError, setFeedError] = useState(false)
  const [yoloEnabled, setYoloEnabled] = useState(false)
  const [settings, setSettings] = useState({ manual_speed: 60, control_mode: 2 })
  
  const keysRef = useRef({})
  const rcInterval = useRef(null)
  const joystickRC = useRef({ lr: 0, fb: 0, ud: 0, yv: 0 })
  const settingsRef = useRef(settings)

  useEffect(() => {
    settingsRef.current = settings
  }, [settings])

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

  const togglePathRecording = async () => {
    if (pathRecording) {
      await post('recorder/stop')
      setPathRecording(false)
      setPathDuration(0)
    } else {
      await post('recorder/start')
      setPathRecording(true)
    }
  }

  const toggleVideoRecording = async () => {
    if (videoRecording) {
      await post('video/stop')
      setVideoRecording(false)
      setVideoDuration(0)
    } else {
      await post('video/start')
      setVideoRecording(true)
    }
  }

  const takePhoto = async () => {
    if (photoFlash) return
    setPhotoFlash(true)
    await post('snapshot')
    setTimeout(() => setPhotoFlash(false), 600)
  }

  useEffect(() => {
    if (!pathRecording) return
    const t = setInterval(() => setPathDuration(d => d + 1), 1000)
    return () => clearInterval(t)
  }, [pathRecording])

  useEffect(() => {
    if (!videoRecording) return
    const t = setInterval(() => setVideoDuration(d => d + 1), 1000)
    return () => clearInterval(t)
  }, [videoRecording])

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

  const fetchSettings = async () => {
    try {
      const res = await fetch('/api/settings/flight')
      if (res.ok) setSettings(await res.json())
    } catch (err) {
      console.error(err)
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchYoloConfig()
      fetchSettings()
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
    const speed = settingsRef.current.manual_speed || 60
    const isMode1 = settingsRef.current.control_mode === 1
    if (isMode1) {
      joystickRC.current.yv = Math.round(x * speed)
      joystickRC.current.ud = Math.round(y * speed)
    } else {
      joystickRC.current.lr = Math.round(x * speed)
      joystickRC.current.fb = Math.round(y * speed)
    }
  }, [])

  const handleRightStick = useCallback((x, y) => {
    const speed = settingsRef.current.manual_speed || 60
    const isMode1 = settingsRef.current.control_mode === 1
    if (isMode1) {
      joystickRC.current.lr = Math.round(x * speed)
      joystickRC.current.fb = Math.round(y * speed)
    } else {
      joystickRC.current.yv = Math.round(x * speed)
      joystickRC.current.ud = Math.round(y * speed)
    }
  }, [])

  // Unified RC send loop (keyboard + joystick)
  useEffect(() => {
    const handleDown = (e) => { keysRef.current[e.key.toLowerCase()] = true }
    const handleUp = (e) => { keysRef.current[e.key.toLowerCase()] = false }
    window.addEventListener('keydown', handleDown)
    window.addEventListener('keyup', handleUp)

    const lastSentRC = { lr: 0, fb: 0, ud: 0, yv: 0 }
    let lastSentTime = 0

    rcInterval.current = setInterval(() => {
      const k = keysRef.current
      const speed = settingsRef.current.manual_speed || 60
      const isMode1 = settingsRef.current.control_mode === 1

      let lr = 0, fb = 0, ud = 0, yv = 0

      const wasd1 = (k['d'] ? speed : 0) - (k['a'] ? speed : 0)
      const wasd2 = (k['w'] ? speed : 0) - (k['s'] ? speed : 0)
      const arrows1 = (k['arrowup'] ? speed : 0) - (k['arrowdown'] ? speed : 0)
      const arrows2 = (k['arrowright'] ? speed : 0) - (k['arrowleft'] ? speed : 0)

      if (isMode1) {
        // Mode 1: WASD is Yaw/Throttle (yv/ud), Arrows is Roll/Pitch (lr/fb)
        yv = wasd1
        ud = wasd2
        fb = arrows1
        lr = arrows2
      } else {
        // Mode 2: WASD is Roll/Pitch (lr/fb), Arrows is Yaw/Throttle (yv/ud)
        lr = wasd1
        fb = wasd2
        ud = arrows1
        yv = arrows2
      }

      const j = joystickRC.current
      lr = lr || j.lr
      fb = fb || j.fb
      ud = ud || j.ud
      yv = yv || j.yv
      
      const changed = lr !== lastSentRC.lr || fb !== lastSentRC.fb || ud !== lastSentRC.ud || yv !== lastSentRC.yv
      const now = Date.now()
      const timeSinceLast = now - lastSentTime
      const isNonZero = lr !== 0 || fb !== 0 || ud !== 0 || yv !== 0

      // Send on change immediately, OR keep-alive every 80ms while holding.
      // Keep-alive interval (80ms) MUST be shorter than the backend watchdog (250ms)
      // so the watchdog never fires while a key is still held down.
      if (changed || (isNonZero && timeSinceLast >= 80)) {
        lastSentRC.lr = lr
        lastSentRC.fb = fb
        lastSentRC.ud = ud
        lastSentRC.yv = yv
        lastSentTime = now
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
          
          <div className="absolute top-2 inset-x-2 flex justify-between text-[10px] font-mono bg-black/75 px-3 py-1.5 rounded-lg border border-white/5 z-20">
            <span>ALT: {telemetry.height}cm</span>
            <span>BAT: {telemetry.battery}%</span>
          </div>

          {/* Minimap Overlay */}
          {telemetry.connected && <FlightMinimap telemetry={telemetry} settings={settings} />}
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
            {settings.control_mode === 1 ? (
              <>
                <div className="flex justify-between"><span className="text-neutral-500">WASD</span> <span>Yaw/Throttle</span></div>
                <div className="flex justify-between"><span className="text-neutral-500">Arrows</span> <span>Pitch/Roll</span></div>
              </>
            ) : (
              <>
                <div className="flex justify-between"><span className="text-neutral-500">WASD</span> <span>Pitch/Roll</span></div>
                <div className="flex justify-between"><span className="text-neutral-500">Arrows</span> <span>Yaw/Throttle</span></div>
              </>
            )}
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
          <div className="absolute top-0 inset-x-0 bg-gradient-to-b from-black/85 to-transparent px-5 py-4 flex justify-between items-center text-[11px] font-mono text-neutral-300 tracking-wide select-none z-20">
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

          {/* Minimap Overlay */}
          {telemetry.connected && <FlightMinimap telemetry={telemetry} settings={settings} />}
        </div>

        {/* Action Controls Panel below Viewport */}
        <div className="mt-5 flex items-center justify-center gap-2">

          {/* ── Flight Path Recorder ── */}
          <div className={`flex items-center rounded-xl border transition-all ${
            pathRecording
              ? 'bg-amber-500/10 border-amber-500/25 px-3 py-1 gap-2'
              : 'bg-white/5 border-white/5 p-1'
          }`}>
            <button
              onClick={togglePathRecording}
              disabled={!telemetry.connected}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer ${
                pathRecording ? 'text-amber-400' : 'text-neutral-400 hover:text-white'
              } disabled:opacity-25`}
              title={pathRecording ? 'Stop Flight Path Recording' : 'Start Flight Path Recording'}
            >
              {pathRecording ? <RouteOff size={14} /> : <Route size={14} />}
            </button>
            {pathRecording && (
              <span className="text-[10px] text-amber-400 font-mono font-bold tracking-wider animate-pulse select-none">
                {formatTime(pathDuration)}
              </span>
            )}
          </div>

          {/* ── Video Recorder ── */}
          <div className={`flex items-center rounded-xl border transition-all ${
            videoRecording
              ? 'bg-danger/10 border-danger/25 px-3 py-1 gap-2'
              : 'bg-white/5 border-white/5 p-1'
          }`}>
            <button
              onClick={toggleVideoRecording}
              disabled={!telemetry.connected}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer ${
                videoRecording ? 'text-danger' : 'text-neutral-400 hover:text-white'
              } disabled:opacity-25`}
              title={videoRecording ? 'Stop Video Recording' : 'Start Video Recording'}
            >
              {videoRecording ? <VideoOff size={14} /> : <Video size={14} />}
            </button>
            {videoRecording && (
              <span className="text-[10px] text-danger font-mono font-bold tracking-wider animate-pulse select-none">
                {formatTime(videoDuration)}
              </span>
            )}
          </div>

          {/* ── Photo Snapshot ── */}
          <button
            onClick={takePhoto}
            disabled={!telemetry.connected}
            className={`w-10 h-10 rounded-xl border flex items-center justify-center transition-all cursor-pointer disabled:opacity-20 ${
              photoFlash
                ? 'bg-white text-slate-950 border-white scale-95'
                : 'bg-white/5 border-white/5 text-neutral-400 hover:text-white hover:bg-white/10'
            }`}
            title="Take Photo Snapshot"
          >
            <Camera size={14} />
          </button>

          {/* ── Toggle Camera direction ── */}
          <button
            onClick={handleCamera}
            disabled={!telemetry.connected}
            className="w-10 h-10 rounded-xl bg-white/5 border border-white/5 text-neutral-400 hover:text-white hover:bg-white/10 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-20"
            title="Switch Camera Direction"
          >
            <SwitchCamera size={14} />
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

function FlightMinimap({ telemetry, settings }) {
  const flightPath = telemetry.flight_path || [];
  const curX = telemetry.pos_x || 0;
  const curY = telemetry.pos_y || 0;
  const curZ = telemetry.height || 0;
  const curYaw = telemetry.yaw || 0;

  // Dynamically calculate the min/max heights from the active flight path
  const zVals = flightPath.map(p => p.z);
  zVals.push(curZ);
  const minZ = Math.min(...zVals);
  const maxZ = Math.max(...zVals);

  const getRange = () => {
    if (flightPath.length === 0) return 10; // 10cm default
    const xVals = flightPath.map(p => p.x);
    const yVals = flightPath.map(p => p.y);
    xVals.push(curX);
    yVals.push(curY);
    
    const maxX = Math.max(...xVals);
    const minX = Math.min(...xVals);
    const maxY = Math.max(...yVals);
    const minY = Math.min(...yVals);
    
    const maxD = Math.max(
      Math.abs(maxX), Math.abs(minX),
      Math.abs(maxY), Math.abs(minY)
    );
    
    if (maxD <= 8) {
      return 10; // 10cm range (rings at 4cm, 8cm)
    } else if (maxD <= 16) {
      return 20; // 20cm range (rings at 8cm, 16cm)
    } else if (maxD <= 40) {
      return 50; // 50cm range (rings at 20cm, 40cm)
    } else if (maxD <= 80) {
      return 100; // 100cm (1m) range (rings at 40cm, 80cm)
    } else if (maxD <= 160) {
      return 200; // 2m range (rings at 0.8m, 1.6m)
    } else if (maxD <= 400) {
      return 500; // 5m range (rings at 2m, 4m)
    } else if (maxD <= 800) {
      return 1000; // 10m range
    } else if (maxD <= 1600) {
      return 2000; // 20m range
    } else if (maxD <= 4000) {
      return 5000; // 50m range
    } else {
      return Math.ceil(maxD / 5000) * 5000; // steps of 50m
    }
  };

  const range = getRange();

  const mapX = (yVal) => 50 + (yVal / range) * 40;
  const mapY = (xVal) => 50 - (xVal / range) * 40;

  const getAltitudeColor = (z) => {
    if (minZ === maxZ) {
      // If height is constant, display trail as stable bright green
      return 'hsl(120, 95%, 50%)';
    }
    const ratio = (z - minZ) / (maxZ - minZ);
    const hue = ratio * 120; // 0 is red, 120 is bright green
    return `hsl(${hue}, 95%, 50%)`;
  };

  const segments = [];
  for (let i = 0; i < flightPath.length - 1; i++) {
    const p1 = flightPath[i];
    const p2 = flightPath[i + 1];
    segments.push({
      x1: mapX(p1.y),
      y1: mapY(p1.x),
      x2: mapX(p2.y),
      y2: mapY(p2.x),
      color: getAltitudeColor((p1.z + p2.z) / 2),
      id: i
    });
  }
  if (flightPath.length > 0) {
    const lastP = flightPath[flightPath.length - 1];
    segments.push({
      x1: mapX(lastP.y),
      y1: mapY(lastP.x),
      x2: mapX(curY),
      y2: mapY(curX),
      color: getAltitudeColor((lastP.z + curZ) / 2),
      id: 'final'
    });
  }

  const droneCx = mapX(curY);
  const droneCy = mapY(curX);
  const droneColor = getAltitudeColor(curZ);
  const homeX = mapX(0);
  const homeY = mapY(0);

  const formatDistance = (cm) => {
    if (cm < 100) return `${Math.round(cm)}cm`;
    return `${(cm / 100).toFixed(0)}m`;
  };

  const formatRange = (cm) => {
    if (cm < 100) return `${Math.round(cm)}cm`;
    return `${(cm / 100).toFixed(1)}m`;
  };

  return (
    <div className="absolute bottom-4 right-4 w-40 h-40 sm:w-48 sm:h-48 rounded-xl border border-white/10 bg-black/80 backdrop-blur-md overflow-hidden flex flex-col p-2 select-none shadow-2xl z-10">
      <div className="flex justify-between text-[9px] font-mono text-neutral-400 px-1 pb-1 border-b border-white/5">
        <span className="font-bold tracking-wider">FLIGHT RADAR</span>
        <span>RNG: {formatRange(range)}</span>
      </div>
      
      <div className="flex-1 relative overflow-hidden flex items-center justify-center my-1">
        <svg className="w-full h-full" viewBox="0 0 100 100">
          <circle cx={50} cy={50} r={16} fill="none" stroke="rgba(255,255,255,0.07)" strokeDasharray="2,2" />
          <circle cx={50} cy={50} r={32} fill="none" stroke="rgba(255,255,255,0.07)" strokeDasharray="2,2" />
          
          <text x={50} y={50 - 16 - 2} textAnchor="middle" fontSize={4.5} fill="rgba(255,255,255,0.35)" fontFamily="monospace">
            {formatDistance(range * 0.4)}
          </text>
          <text x={50} y={50 - 32 - 2} textAnchor="middle" fontSize={4.5} fill="rgba(255,255,255,0.35)" fontFamily="monospace">
            {formatDistance(range * 0.8)}
          </text>

          <line x1={15} y1={50} x2={85} y2={50} stroke="rgba(255,255,255,0.05)" strokeWidth={0.5} strokeDasharray="1,2" />
          <line x1={50} y1={15} x2={50} y2={85} stroke="rgba(255,255,255,0.05)" strokeWidth={0.5} strokeDasharray="1,2" />
          
          {segments.map((seg, idx) => (
            <g key={seg.id || idx}>
              <line x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2} stroke={seg.color} strokeWidth={3} strokeLinecap="round" opacity={0.25} />
              <line x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2} stroke={seg.color} strokeWidth={1.2} strokeLinecap="round" />
            </g>
          ))}
          
          <g transform={`translate(${homeX}, ${homeY})`}>
            <circle r={3} fill="#f59e0b" opacity={0.2} />
            <rect x={-3} y={-3} width={6} height={6} fill="none" stroke="#f59e0b" strokeWidth={0.75} rx={0.5} />
            <text x={0} y={2.2} textAnchor="middle" fontSize={5} fontWeight="bold" fill="#f59e0b" fontFamily="monospace">H</text>
          </g>
          
          <g transform={`translate(${droneCx}, ${droneCy}) rotate(${curYaw})`}>
            <circle r={6} fill={droneColor} opacity={0.3} className="animate-pulse" />
            <circle r={4} fill="none" stroke="#ffffff" strokeWidth={0.75} />
            <circle r={2.2} fill={droneColor} />
            <line x1={0} y1={0} x2={0} y2={-5} stroke="#ffffff" strokeWidth={1} />
          </g>
        </svg>
      </div>
      
      <div className="mt-auto pt-1.5 border-t border-white/5 flex flex-col gap-1 w-full text-[9px] font-mono">
        <div className="flex justify-between text-neutral-400">
          <span>ALTITUDE GRADIENT</span>
          <span className="text-white font-bold">{curZ}cm</span>
        </div>
        <div className="relative h-1 w-full rounded-full overflow-hidden bg-white/10 flex">
          <div className="absolute inset-0 bg-gradient-to-r from-red-500 via-yellow-400 to-green-500" />
          <div 
            className="absolute w-1 h-2 -top-[2px] bg-white border border-black/45 rounded-sm shadow-sm transition-all duration-300"
            style={{ 
              left: `${minZ === maxZ ? 100 : Math.min(100, Math.max(0, ((curZ - minZ) / (maxZ - minZ)) * 100))}%` 
            }}
          />
        </div>
        <div className="flex justify-between text-[7px] text-neutral-500">
          <span>Lowest ({formatDistance(minZ)})</span>
          <span>Highest ({formatDistance(maxZ)})</span>
        </div>
      </div>
    </div>
  );
}
