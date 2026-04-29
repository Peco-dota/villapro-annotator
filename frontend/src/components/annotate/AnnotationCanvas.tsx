import { useRef, useState, useCallback, useEffect } from 'react'
import { Stage, Layer, Image as KonvaImage, Rect, Transformer } from 'react-konva'
import Konva from 'konva'
import type { BoundingBox, ClassDef } from '../../lib/types'
import { getImageFile } from '../../lib/api'

interface Props {
  projectPath: string
  filename: string
  boxes: BoundingBox[]
  classes: ClassDef[]
  selectedClass: number
  tool: 'draw' | 'select'
  selectedBoxId: string | null
  onSelectBox: (id: string | null) => void
  onBoxesChange: (boxes: BoundingBox[]) => void
  onSelectClass: (i: number) => void
  zoom: number                        // multiplier: 1 = fit, >1 = zoomed in
  onZoomChange: (z: number) => void
  onFitScaleChange?: (fs: number) => void
}

interface PendingBox {
  box: BoundingBox
  screenX: number
  screenY: number
}

function useImage(src: string) {
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [imgError, setImgError] = useState(false)
  useEffect(() => {
    if (!src) return
    setImgError(false)
    const el = new window.Image()
    el.crossOrigin = 'anonymous'
    el.onload = () => { setImg(el); setSize({ w: el.naturalWidth, h: el.naturalHeight }) }
    el.onerror = () => { setImg(null); setImgError(true) }
    el.src = src
    return () => { el.onload = null; el.onerror = null }
  }, [src])
  return { img, naturalW: size.w, naturalH: size.h, imgError }
}

function uuid() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
  })
}

function ClassPickerPopup({ classes, screenX, screenY, onPick, onCancel }: {
  classes: ClassDef[]
  screenX: number
  screenY: number
  onPick: (i: number) => void
  onCancel: () => void
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
      const n = parseInt(e.key)
      if (n >= 1 && n <= 9 && n - 1 < classes.length) onPick(n - 1)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [classes, onPick, onCancel])

  return (
    <div
      className="absolute z-20 bg-[#0f172a] border border-[#334155] rounded-lg shadow-xl py-1 min-w-36"
      style={{ left: screenX, top: screenY }}
      onClick={e => e.stopPropagation()}
    >
      <p className="text-[10px] text-slate-500 px-3 py-1 uppercase tracking-wider font-semibold">Assign class</p>
      {classes.map((cls, i) => (
        <button
          key={i}
          onClick={() => onPick(i)}
          className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-[#1e293b] cursor-pointer text-left"
        >
          <span className="w-3 h-3 rounded-sm shrink-0" style={{ background: cls.color }} />
          <span className="text-sm text-slate-200 flex-1">{cls.name}</span>
          <span className="text-[10px] text-slate-600">{i + 1}</span>
        </button>
      ))}
      <div className="border-t border-[#1e293b] mt-1 pt-1">
        <button
          onClick={onCancel}
          className="w-full text-left px-3 py-1 text-xs text-slate-500 hover:text-slate-300 cursor-pointer"
        >
          Cancel (Esc)
        </button>
      </div>
    </div>
  )
}

export function AnnotationCanvas({
  projectPath, filename, boxes, classes, selectedClass, tool,
  selectedBoxId, onSelectBox, onBoxesChange, onSelectClass,
  zoom, onZoomChange, onFitScaleChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const trRef = useRef<Konva.Transformer>(null)
  const [stageSize, setStageSize] = useState({ w: 800, h: 600 })
  const [fitScale, setFitScale] = useState(1)  // scale that fits image to window
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 })
  const [drawing, setDrawing] = useState<{ x: number; y: number } | null>(null)
  const [draft, setDraft] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const [pending, setPending] = useState<PendingBox | null>(null)
  const isPanning = useRef(false)
  const panStart = useRef({ x: 0, y: 0 })
  const panOffsetStart = useRef({ x: 0, y: 0 })

  const imgSrc = filename ? getImageFile(projectPath, filename) : ''
  const { img, naturalW, naturalH, imgError } = useImage(imgSrc)

  // scale = fitScale * zoom, offset centers image then adjusts for pan
  const scale = fitScale * zoom
  const offset = {
    x: (stageSize.w - naturalW * scale) / 2 + panOffset.x,
    y: (stageSize.h - naturalH * scale) / 2 + panOffset.y,
  }

  // recalculate fit scale on resize or new image
  useEffect(() => {
    const el = containerRef.current
    if (!el || !naturalW || !naturalH) return
    const measure = () => {
      const cw = el.clientWidth
      const ch = el.clientHeight
      setStageSize({ w: cw, h: ch })
      const fs = Math.min(cw / naturalW, ch / naturalH, 1)
      setFitScale(fs)
      onFitScaleChange?.(fs)
    }
    measure()
    const obs = new ResizeObserver(measure)
    obs.observe(el)
    return () => obs.disconnect()
  }, [naturalW, naturalH])

  // reset pan when image changes
  useEffect(() => { setPanOffset({ x: 0, y: 0 }) }, [filename])

  // attach transformer
  useEffect(() => {
    if (!trRef.current || !stageRef.current) return
    if (selectedBoxId) {
      const node = stageRef.current.findOne(`#box-${selectedBoxId}`)
      if (node) trRef.current.nodes([node])
    } else {
      trRef.current.nodes([])
    }
    trRef.current.getLayer()?.batchDraw()
  }, [selectedBoxId, boxes])

  // scroll-wheel zoom
  const handleWheel = useCallback((e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault()
    const delta = e.evt.deltaY < 0 ? 1.1 : 1 / 1.1
    onZoomChange(Math.max(0.1, Math.min(zoom * delta, 8)))
  }, [zoom, onZoomChange])

  const toNorm = useCallback((px: number, py: number) => ({
    nx: (px - offset.x) / (naturalW * scale),
    ny: (py - offset.y) / (naturalH * scale),
  }), [offset, naturalW, naturalH, scale])

  const getColor = (idx: number) => classes[idx]?.color ?? '#a78bfa'

  const handleMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (pending) return
    // Middle-click or space+left = pan
    if (e.evt.button === 1 || (e.evt.button === 0 && e.evt.altKey)) {
      isPanning.current = true
      panStart.current = { x: e.evt.clientX, y: e.evt.clientY }
      panOffsetStart.current = { ...panOffset }
      return
    }
    if (tool !== 'draw') return
    if (!img) return
    const pos = e.target.getStage()!.getPointerPosition()!
    setDrawing({ x: pos.x, y: pos.y })
    setDraft(null)
    onSelectBox(null)
  }

  const handleMouseMove = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (isPanning.current) {
      setPanOffset({
        x: panOffsetStart.current.x + (e.evt.clientX - panStart.current.x),
        y: panOffsetStart.current.y + (e.evt.clientY - panStart.current.y),
      })
      return
    }
    if (!drawing) return
    const pos = e.target.getStage()!.getPointerPosition()!
    setDraft({
      x: Math.min(drawing.x, pos.x),
      y: Math.min(drawing.y, pos.y),
      w: Math.abs(pos.x - drawing.x),
      h: Math.abs(pos.y - drawing.y),
    })
  }

  const handleMouseUp = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (isPanning.current) { isPanning.current = false; return }
    if (!drawing || !draft || draft.w < 5 || draft.h < 5) {
      setDrawing(null); setDraft(null); return
    }
    const cx_px = draft.x + draft.w / 2
    const cy_px = draft.y + draft.h / 2
    const { nx: cx, ny: cy } = toNorm(cx_px, cy_px)
    const w = draft.w / (naturalW * scale)
    const h = draft.h / (naturalH * scale)

    if (cx < 0 || cy < 0 || cx > 1 || cy > 1) { setDrawing(null); setDraft(null); return }

    const box: BoundingBox = {
      id: uuid(),
      class_index: selectedClass,
      cx: Math.max(0, Math.min(1, cx)),
      cy: Math.max(0, Math.min(1, cy)),
      w: Math.min(w, 1),
      h: Math.min(h, 1),
    }

    setDrawing(null)
    setDraft(null)

    if (classes.length <= 1) {
      onBoxesChange([...boxes, box])
      onSelectBox(box.id)
    } else {
      const popupX = Math.min(draft.x + draft.w + 8, stageSize.w - 160)
      const popupY = Math.min(draft.y, stageSize.h - 200)
      setPending({ box, screenX: popupX, screenY: popupY })
      void e
    }
  }

  const commitPending = useCallback((classIndex: number) => {
    if (!pending) return
    const box = { ...pending.box, class_index: classIndex }
    onSelectClass(classIndex)
    onBoxesChange([...boxes, box])
    onSelectBox(box.id)
    setPending(null)
  }, [pending, boxes, onBoxesChange, onSelectBox, onSelectClass])

  const handleBoxClick = (id: string) => {
    if (tool === 'select') onSelectBox(id === selectedBoxId ? null : id)
  }

  const handleBoxTransformEnd = (id: string, node: Konva.Rect) => {
    const scaleX = node.scaleX(); const scaleY = node.scaleY()
    node.scaleX(1); node.scaleY(1)
    const x = node.x() + node.width() * scaleX / 2
    const y = node.y() + node.height() * scaleY / 2
    const { nx: cx, ny: cy } = toNorm(x, y)
    const w = (node.width() * scaleX) / (naturalW * scale)
    const h = (node.height() * scaleY) / (naturalH * scale)
    onBoxesChange(boxes.map(b => b.id === id
      ? { ...b, cx: Math.max(0, Math.min(1, cx)), cy: Math.max(0, Math.min(1, cy)), w: Math.min(w, 1), h: Math.min(h, 1) }
      : b
    ))
  }

  const handleDragEnd = (id: string, node: Konva.Rect) => {
    const cx_px = node.x() + node.width() / 2
    const cy_px = node.y() + node.height() / 2
    const { nx: cx, ny: cy } = toNorm(cx_px, cy_px)
    onBoxesChange(boxes.map(b => b.id === id
      ? { ...b, cx: Math.max(0, Math.min(1, cx)), cy: Math.max(0, Math.min(1, cy)) }
      : b
    ))
  }

  const boxToRect = (b: BoundingBox) => ({
    x: offset.x + (b.cx - b.w / 2) * naturalW * scale,
    y: offset.y + (b.cy - b.h / 2) * naturalH * scale,
    width: b.w * naturalW * scale,
    height: b.h * naturalH * scale,
  })

  const draftColor = getColor(pending ? pending.box.class_index : selectedClass)
  const cursor = isPanning.current ? 'grabbing' : tool === 'draw' ? 'crosshair' : 'default'

  return (
    <div ref={containerRef} className="flex-1 overflow-hidden relative" style={{ background: '#2a2a2a', cursor }}>
      <Stage
        ref={stageRef}
        width={stageSize.w}
        height={stageSize.h}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
        onClick={(e) => { if (e.target === e.target.getStage() && !pending) onSelectBox(null) }}
      >
        <Layer>
          {img && (
            <KonvaImage
              image={img}
              x={offset.x} y={offset.y}
              width={naturalW * scale}
              height={naturalH * scale}
            />
          )}

          {boxes.map(b => {
            const r = boxToRect(b)
            const color = getColor(b.class_index)
            return (
              <Rect
                key={b.id}
                id={`box-${b.id}`}
                x={r.x} y={r.y} width={r.width} height={r.height}
                stroke={color}
                strokeWidth={selectedBoxId === b.id ? 2 : 1.5}
                fill={selectedBoxId === b.id ? color + '22' : color + '11'}
                draggable={tool === 'select'}
                onClick={() => handleBoxClick(b.id)}
                onDragEnd={e => handleDragEnd(b.id, e.target as Konva.Rect)}
                onTransformEnd={e => handleBoxTransformEnd(b.id, e.target as Konva.Rect)}
              />
            )
          })}

          {pending && (() => {
            const r = boxToRect(pending.box)
            return (
              <Rect
                x={r.x} y={r.y} width={r.width} height={r.height}
                stroke={draftColor} strokeWidth={1.5} fill={draftColor + '22'}
                dash={[4, 4]} listening={false}
              />
            )
          })()}

          {draft && !pending && (
            <Rect
              x={draft.x} y={draft.y} width={draft.w} height={draft.h}
              stroke={draftColor} strokeWidth={1.5} fill={draftColor + '22'}
              dash={[4, 4]} listening={false}
            />
          )}

          <Transformer
            ref={trRef}
            rotateEnabled={false}
            boundBoxFunc={(_, newBox) => ({ ...newBox, width: Math.max(10, newBox.width), height: Math.max(10, newBox.height) })}
          />
        </Layer>
      </Stage>

      {pending && (
        <ClassPickerPopup
          classes={classes}
          screenX={pending.screenX}
          screenY={pending.screenY}
          onPick={commitPending}
          onCancel={() => setPending(null)}
        />
      )}

      {imgError && filename && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center px-6">
          <span className="text-red-400 text-sm font-medium">Image not found</span>
          <span className="text-slate-500 text-xs font-mono">{filename}</span>
          <span className="text-slate-600 text-xs">Make sure images are in the container-accessible path (e.g. /villapro-data/…)</span>
        </div>
      )}
      {!img && !imgError && filename && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Zoom indicator */}
      <div className="absolute bottom-2 right-2 text-[10px] text-slate-600 bg-[#0f172a]/70 px-2 py-0.5 rounded pointer-events-none">
        {Math.round(zoom * 100)}%
      </div>
    </div>
  )
}
