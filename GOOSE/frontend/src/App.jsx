import { Routes, Route, NavLink } from 'react-router-dom'
import { Plane, Image, Settings, Lightbulb, Wifi, WifiOff, Battery, ServerOff } from 'lucide-react'
import { useState, useEffect } from 'react'
import Dashboard from './pages/Dashboard'
import MediaGallery from './pages/MediaGallery'
import LEDManager from './pages/LEDManager'
import SettingsPage from './pages/Settings'

function App() {
  const [telemetry, setTelemetry] = useState({
    connected: false, flying: false, ip: '', drone_name: '',
    battery: 0, height: 0, speed_x: 0, speed_y: 0, speed_z: 0, speed: 0,
    pitch: 0, roll: 0, yaw: 0, temperature: 0, flight_duration: 0, total_distance: 0,
    autopilot_active: false, autopilot_phase: 'OFF',
    pos_x: 0.0, pos_y: 0.0, flight_path: [],
  })
  const [serverOnline, setServerOnline] = useState(true)

  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const res = await fetch('/api/telemetry')
        if (res.ok) {
          setTelemetry(await res.json())
          setServerOnline(true)
        } else {
          setServerOnline(false)
        }
      } catch {
        setServerOnline(false)
      }
    }, 250)
    return () => clearInterval(poll)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-[#090a0c] font-sans">
      {/* Integrated Left Navigation Rail */}
      <nav className="w-16 h-full bg-[#0c0d0f] border-r border-white/5 flex flex-col items-center py-5 gap-3 shrink-0 z-20">
        <div className="mb-4 text-white font-bold text-xs tracking-wider font-title flex items-center justify-center w-8 h-8 rounded-lg bg-white/5 border border-white/10">
          G
        </div>
        <NavItem to="/" icon={<Plane size={16} />} label="Fly" />
        <NavItem to="/led" icon={<Lightbulb size={16} />} label="LED" />
        <NavItem to="/media" icon={<Image size={16} />} label="Media" />
        <NavItem to="/settings" icon={<Settings size={16} />} label="Settings" />
        
        {/* Status Indicators at Bottom of Sidebar */}
        <div className="mt-auto flex flex-col items-center gap-4 pt-4 border-t border-white/5 w-10 text-xs">
          {!serverOnline ? (
            <div className="text-warning" title="Backend offline">
              <ServerOff size={14} />
            </div>
          ) : telemetry.connected ? (
            <div className="text-success" title="Drone connected">
              <Wifi size={14} />
            </div>
          ) : (
            <div className="text-neutral-500" title="Drone disconnected">
              <WifiOff size={14} />
            </div>
          )}
          <div className="flex flex-col items-center gap-0.5 text-neutral-500 font-medium font-display">
            <Battery size={13} className={telemetry.battery > 20 ? 'text-success' : 'text-danger'} />
            <span className="text-[8px] tabular-nums">{telemetry.battery}%</span>
          </div>
        </div>
      </nav>

      {/* Main View Container */}
      <main className="flex-1 h-screen overflow-hidden bg-transparent relative flex flex-col">
        {!serverOnline && (
          <div className="bg-warning/10 border-b border-warning/10 px-4 py-2 text-center text-xs text-warning flex items-center justify-center gap-2 z-50">
            <ServerOff size={13} />
            <span>Backend server offline — start it with <code className="bg-black/40 px-1.5 py-0.5 rounded text-[10px] font-mono border border-white/5">python GOOSE/web_server.py</code></span>
          </div>
        )}
        <div className="flex-1 overflow-y-auto scroll-smooth">
          <Routes>
            <Route path="/" element={<Dashboard telemetry={telemetry} />} />
            <Route path="/led" element={<LEDManager />} />
            <Route path="/media" element={<MediaGallery telemetry={telemetry} />} />
            <Route path="/settings" element={<SettingsPage telemetry={telemetry} />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

function NavItem({ to, icon, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `w-12 h-12 rounded-lg flex flex-col items-center justify-center gap-1 text-[9px] tracking-wider uppercase font-semibold transition-all ${
          isActive
            ? 'bg-white/5 text-white border border-white/10'
            : 'text-neutral-500 hover:text-neutral-300 border border-transparent'
        }`
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  )
}

export default App
