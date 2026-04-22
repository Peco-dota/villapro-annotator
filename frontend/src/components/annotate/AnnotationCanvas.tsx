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
  onBoxesChange: (boxes: BoundingBox[]) => void
}

function useImage(src: string) {
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    if (!src) return
    const el = new window.Image()
    el.crossOrigin = 'anonymous'
    el.onload = () => { setImg(el); setSize({ w: el.naturalWidth, h: el.naturalHeight }) }
    el.src = src
    return () => { el.onload = null }
  }, [src])
  return { img, naturalW: size.w, naturalH: size.h }
}

function uuid() {
  return crypto.randomUUID()
}

export function AnnotationCanvas({ projectPath, filename, boxes, classes, selectedClass, tool, onBoxesChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const trRef = useRef<Konva.Transformer>(null)
  const [stageSize, setStageSize] = useState({ w: 800, h: 600 })
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [drawing, setDrawing] = useState<{ x: number; y: number } | null>(null)
  const [draft, setDraft] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const imgSrc = filename ? getImageFile(projectPath, filename) : ''
  const { img, naturalW, naturalH } = useImage(imgSrc)

  // fit image to canvas
  useEffect(() => {
    const el = containerRef.current
    if (!el || !naturalW || !naturalH) return
    const obs = new ResizeObserver(() => {
      const cw = el.clientWidth
      const ch = el.clientHeight
      setStageSize({ w: cw, h: ch })
      const sc = Math.min(cw / naturalW, ch / naturalH, 1)
      setScale(sc)
      setOffset({
        x: (cw - naturalW * sc) / 2,
        y: (ch - naturalH * sc) / 2,
      })
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [naturalW, naturalH])

  useEffect(() => { setSelectedId(null) }, [filename])

  // attach transformer to selected node
  useEffect(() => {
    if (!trRef.current || !stageRef.current) return
    if (selectedId) {
      const node = stageRef.current.findOne(`#box-${selectedId}`)
      if (node) trRef.current.nodes([node])
    } else {
      trRef.current.nodes([])
    }
    trRef.current.getLayer()?.batchDraw()
  }, [selectedId, boxes])

  const toNorm = useCallback((px: number, py: number) => ({
    nx: (px - offset.x) / (naturalW * scale),
    ny: (py - offset.y) / (naturalH * scale),
  }), [offset, naturalW, naturalH, scale])

  const getColor = (idx: number) => classes[idx]?.color ?? '#a78bfa'

  const handleMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (tool !== 'draw') return
    const pos = e.target.getStage()!.getPointerPosition()!
    setDrawing({ x: pos.x, y: pos.y })
    setDraft(null)
    setSelectedId(null)
  }

  const handleMouseMove = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (!drawing) return
    const pos = e.target.getStage()!.getPointerPosition()!
    setDraft({
      x: Math.min(drawing.x, pos.x),
      y: Math.min(drawing.y, pos.y),
      w: Math.abs(pos.x - drawing.x),
      h: Math.abs(pos.y - drawing.y),
    })
  }

  const handleMouseUp = () => {
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
    onBoxesChange([...boxes, box])
    setDrawing(null)
    setDraft(null)
    setSelectedId(box.id)
  }

  const handleBoxClick = (id: string) => {
    if (tool === 'select') setSelectedId(id === selectedId ? null : id)
  }

  const handleBoxTransformEnd = (id: string, node: Konva.Rect) => {
    const scaleX = node.scaleX()
    const scaleY = node.scaleY()
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

  const deleteSelected = useCallback(() => {
    if (selectedId) {
      onBoxesChange(boxes.filter(b => b.id !== selectedId))
      setSelectedId(null)
    }
  }, [selectedId, boxes, onBoxesChange])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        const tag = (e.target as HTMLElement).tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA') return
        deleteSelected()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [deleteSelected, selectedId])

  const boxToRect = (b: BoundingBox) => ({
    x: offset.x + (b.cx - b.w / 2) * naturalW * scale,
    y: offset.y + (b.cy - b.h / 2) * naturalH * scale,
    width: b.w * naturalW * scale,
    height: b.h * naturalH * scale,
  })

  return (
    <div ref={containerRef} className="flex-1 overflow-hidden bg-[#0c0a14] relative" style={{ cursor: tool === 'draw' ? 'crosshair' : 'default' }}>
      <Stage
        ref={stageRef}
        width={stageSize.w}
        height={stageSize.h}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onClick={(e) => { if (e.target === e.target.getStage()) setSelectedId(null) }}
      >
        <Layer>
          {img && (
            <KonvaImage
              image={img}
              x={offset.x}
              y={offset.y}
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
                strokeWidth={selectedId === b.id ? 2 : 1.5}
                fill={selectedId === b.id ? color + '22' : color + '11'}
                draggable={tool === 'select'}
                onClick={() => handleBoxClick(b.id)}
                onDragEnd={e => handleDragEnd(b.id, e.target as Konva.Rect)}
                onTransformEnd={e => handleBoxTransformEnd(b.id, e.target as Konva.Rect)}
              />
            )
          })}

          {draft && (
            <Rect
              x={draft.x} y={draft.y} width={draft.w} height={draft.h}
              stroke={getColor(selectedClass)}
              strokeWidth={1.5}
              fill={getColor(selectedClass) + '22'}
              dash={[4, 4]}
              listening={false}
            />
          )}

          <Transformer
            ref={trRef}
            rotateEnabled={false}
            boundBoxFunc={(_, newBox) => ({ ...newBox, width: Math.max(10, newBox.width), height: Math.max(10, newBox.height) })}
          />
        </Layer>
      </Stage>

      {!img && filename && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}
    </div>
  )
}
