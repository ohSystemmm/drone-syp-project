import { useState, useEffect } from 'react'
import { Grid, List, Trash2, Image, Film, X, RefreshCw, Layers, Check } from 'lucide-react'

export default function MediaGallery() {
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState('grid')
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(new Set())
  const [selectionMode, setSelectionMode] = useState(false)
  const [preview, setPreview] = useState(null)

  const fetchMedia = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/media')
      if (res.ok) {
        const data = await res.json()
        setFiles(data)
      }
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchMedia()
    }, 0)
    return () => clearTimeout(timer)
  }, [])

  const displayed = files.filter(f => {
    if (filter === 'photos') return f.type === 'photo'
    if (filter === 'videos') return f.type === 'video'
    return true
  })

  const toggleSelect = (id) => {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelected(next)
  }

  const deleteSelected = async () => {
    if (!confirm(`Delete ${selected.size} file(s)?`)) return
    for (const id of selected) {
      const file = files.find(f => f.id === id)
      if (file) await fetch(`/api/media/${file.path}`, { method: 'DELETE' })
    }
    setSelected(new Set())
    fetchMedia()
  }

  const deleteSingle = async (file) => {
    if (!confirm(`Delete ${file.name}?`)) return
    await fetch(`/api/media/${file.path}`, { method: 'DELETE' })
    fetchMedia()
  }

  const getThumbUrl = (file) => `/api/media/file/${file.path}`

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-6">
      {/* Header Deck */}
      <div className="flex items-center justify-between pb-3 border-b border-white/5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white">Media Storage</h1>
          <p className="text-xs text-neutral-500 mt-1">{files.length} items stored on drone flight directory</p>
        </div>
        <div className="flex items-center gap-1.5">
          {/* Refresh */}
          <button
            onClick={fetchMedia}
            className="p-2 rounded-lg text-neutral-400 hover:text-white bg-white/5 border border-white/5 hover:bg-white/10 active:scale-95 transition-colors cursor-pointer"
            title="Refresh list"
          >
            <RefreshCw size={13} />
          </button>
          
          {/* Select Toggle */}
          <button
            onClick={() => { setSelectionMode(!selectionMode); setSelected(new Set()) }}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border cursor-pointer ${
              selectionMode 
                ? 'bg-white text-slate-950 border-white' 
                : 'bg-white/5 border-white/5 text-neutral-300 hover:bg-white/10 hover:text-white'
            }`}
          >
            {selectionMode ? 'Cancel' : 'Select'}
          </button>

          <div className="w-px h-5 bg-white/10 mx-1" />

          {/* View Toggles */}
          <button
            onClick={() => setView('grid')}
            className={`p-2 rounded-lg border transition-colors cursor-pointer ${
              view === 'grid' 
                ? 'bg-white/5 border-white/10 text-white' 
                : 'border-transparent text-neutral-500 hover:text-neutral-300'
            }`}
          >
            <Grid size={13} />
          </button>
          <button
            onClick={() => setView('list')}
            className={`p-2 rounded-lg border transition-colors cursor-pointer ${
              view === 'list' 
                ? 'bg-white/5 border-white/10 text-white' 
                : 'border-transparent text-neutral-500 hover:text-neutral-300'
            }`}
          >
            <List size={13} />
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-1.5 p-1 rounded-lg bg-[#121316] border border-white/5 w-fit">
        {['all', 'photos', 'videos'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-md text-xs font-semibold capitalize transition-colors cursor-pointer ${
              filter === f
                ? 'bg-white/5 text-white'
                : 'text-neutral-500 hover:text-neutral-300'
            }`}
          >
            {f === 'all' 
              ? `All (${files.length})` 
              : f === 'photos' 
              ? `Photos (${files.filter(x=>x.type==='photo').length})` 
              : `Videos (${files.filter(x=>x.type==='video').length})`}
          </button>
        ))}
      </div>

      {/* Display content */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-24 text-neutral-500">
          <RefreshCw size={20} className="animate-spin mb-2" />
          <span className="text-xs">Fetching flight media...</span>
        </div>
      ) : displayed.length === 0 ? (
        <div className="text-center py-16 border border-white/5 rounded-xl bg-white/[0.01] p-8 max-w-sm mx-auto">
          <Layers size={32} className="mx-auto mb-3 text-neutral-700" />
          <h3 className="text-xs font-bold text-neutral-300 uppercase tracking-wider mb-1">No media logs</h3>
          <p className="text-xs text-neutral-500 leading-relaxed">No camera captures located. Perform a flight and record feed to capture images.</p>
        </div>
      ) : view === 'grid' ? (
        /* GRID LAYOUT */
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {displayed.map(file => (
            <div
              key={file.id}
              onClick={() => selectionMode ? toggleSelect(file.id) : setPreview(file)}
              className={`group relative rounded-xl overflow-hidden cursor-pointer border bg-[#121316] transition-colors ${
                selected.has(file.id) 
                  ? 'border-white' 
                  : 'border-white/5 hover:border-white/10'
              }`}
            >
              {/* Media Thumbnail */}
              <div className="aspect-video bg-slate-950/20 overflow-hidden relative">
                {file.type === 'photo' ? (
                  <img
                    src={getThumbUrl(file)}
                    alt={file.name}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center bg-[#0d0e11]">
                    <Film size={24} className="text-neutral-600" />
                  </div>
                )}
                {file.type === 'video' && (
                  <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[8px] font-bold bg-black/80 text-white tracking-widest uppercase border border-white/5">
                    Video
                  </span>
                )}
              </div>
              
              {/* Card Label */}
              <div className="p-3 border-t border-white/5 flex flex-col gap-0.5">
                <p className="text-xs font-semibold truncate text-neutral-200">{file.name}</p>
                <p className="text-[10px] text-neutral-500 font-mono flex items-center justify-between">
                  <span>{file.date}</span>
                  <span>{file.size}</span>
                </p>
              </div>

              {/* Selection Checkbox */}
              {selectionMode && (
                <div className="absolute top-2 left-2 z-10">
                  <div className={`w-5 h-5 rounded border flex items-center justify-center transition-all ${
                    selected.has(file.id) 
                      ? 'bg-white border-white' 
                      : 'border-white/20 bg-black/40 hover:border-white/40'
                  }`}>
                    {selected.has(file.id) && <Check size={12} className="text-black stroke-[3px]" />}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        /* LIST LAYOUT */
        <div className="space-y-1.5 max-w-4xl mx-auto">
          {displayed.map(file => (
            <div
              key={file.id}
              onClick={() => selectionMode ? toggleSelect(file.id) : setPreview(file)}
              className={`flex items-center gap-4 p-3 rounded-lg cursor-pointer transition-colors border ${
                selected.has(file.id)
                  ? 'bg-white/5 border-white/10'
                  : 'bg-white/[0.01] border-white/5 hover:bg-white/[0.02] hover:border-white/10'
              }`}
            >
              {selectionMode && (
                <div className={`w-4 h-4 rounded border flex items-center justify-center transition-all shrink-0 ${
                  selected.has(file.id) 
                    ? 'bg-white border-white' 
                    : 'border-white/20 bg-black/40'
                }`}>
                  {selected.has(file.id) && <span className="text-black text-[9px] font-bold">✓</span>}
                </div>
              )}
              {file.type === 'photo' 
                ? <Image size={13} className="text-neutral-500 shrink-0" /> 
                : <Film size={13} className="text-neutral-500 shrink-0" />}
              <span className="flex-1 text-xs font-semibold truncate text-neutral-300">{file.name}</span>
              <span className="text-[10px] text-neutral-500 font-mono">{file.date}</span>
              <span className="text-[10px] text-neutral-500 font-mono w-20 text-right tabular-nums">{file.size}</span>
              <button
                onClick={(e) => { e.stopPropagation(); deleteSingle(file) }}
                className="p-1.5 rounded hover:bg-danger/10 text-neutral-500 hover:text-danger transition-colors cursor-pointer"
                title="Delete file"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Bulk Action Toolbar */}
      {selected.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-[#121316] border border-white/10 rounded-xl px-4 py-2.5 flex items-center gap-4 shadow-2xl z-50">
          <span className="text-xs font-bold text-neutral-300 font-mono">{selected.size} items selected</span>
          <div className="w-px h-3.5 bg-white/10" />
          <button
            onClick={deleteSelected}
            className="p-1.5 rounded-lg bg-danger/10 border border-danger/15 hover:bg-danger/25 text-danger transition-all cursor-pointer"
            title="Delete Selected"
          >
            <Trash2 size={13} />
          </button>
        </div>
      )}

      {/* Cinematic Preview Modal */}
      {preview && (
        <div 
          className="fixed inset-0 bg-[#090a0c]/90 flex items-center justify-center z-50 p-6"
          onClick={() => setPreview(null)}
        >
          <div 
            className="relative max-w-3xl w-full flex flex-col items-center bg-[#121316] p-4 rounded-2xl border border-white/10 shadow-2xl" 
            onClick={e => e.stopPropagation()}
          >
            <button 
              onClick={() => setPreview(null)} 
              className="absolute -top-3 -right-3 w-8 h-8 rounded-full bg-neutral-900 border border-white/10 flex items-center justify-center text-neutral-400 hover:text-white cursor-pointer shadow-lg"
              title="Close"
            >
              <X size={14} />
            </button>
            
            <div className="w-full aspect-video rounded-lg overflow-hidden bg-black flex items-center justify-center border border-white/5">
              {preview.type === 'photo' ? (
                <img src={getThumbUrl(preview)} alt={preview.name} className="max-w-full max-h-[70vh] object-contain" />
              ) : (
                <video src={getThumbUrl(preview)} controls className="max-w-full max-h-[70vh] object-contain" autoPlay />
              )}
            </div>
            
            <div className="mt-3.5 text-center space-y-0.5">
              <p className="text-xs font-bold text-neutral-200">{preview.name}</p>
              <p className="text-[10px] text-neutral-500 font-mono uppercase">
                {preview.size} &bull; {preview.date}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
