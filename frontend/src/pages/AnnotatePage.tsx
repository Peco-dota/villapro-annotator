import { useState, useCallback, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getProjectInfo, getProjectImages, getAnnotations,
  replaceAnnotations, saveProject, copyFromPrev, getClasses,
} from '../lib/api'
import type { BoundingBox, ClassDef, ImageEntry, ProjectInfo } from '../lib/types'
import { ImageList } from '../components/annotate/ImageList'
import { AnnotationCanvas } from '../components/annotate/AnnotationCanvas'
import { ClassSidebar } from '../components/annotate/ClassSidebar'
import { Toolbar } from '../components/annotate/Toolbar'
import { ExportDialog } from '../components/annotate/ExportDialog'
import { TrainDialog } from '../components/annotate/TrainDialog'
import { Spinner } from '../components/ui/Spinner'

const UNDO_LIMIT = 50

export function AnnotatePage() {
  const [params] = useSearchParams()
  const projectPath = params.get('project') ?? ''
  const nav = useNavigate()
  const qc = useQueryClient()

  const [currentFile, setCurrentFile] = useState<string | null>(null)
  const [tool, setTool] = useState<'draw' | 'select'>('draw')
  const [selectedClass, setSelectedClass] = useState(0)
  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null)
  const [boxes, setBoxesState] = useState<BoundingBox[]>([])
  const [undoStack, setUndoStack] = useState<BoundingBox[][]>([])
  const [redoStack, setRedoStack] = useState<BoundingBox[][]>([])
  const [exportOpen, setExportOpen] = useState(false)
  const [trainOpen, setTrainOpen] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [fitScale, setFitScale] = useState(1)

  const { data: info, isLoading: infoLoading } = useQuery<ProjectInfo>({
    queryKey: ['project', projectPath],
    queryFn: () => getProjectInfo(projectPath),
    enabled: !!projectPath,
  })

  const { data: images = [] } = useQuery<ImageEntry[]>({
    queryKey: ['images', projectPath],
    queryFn: () => getProjectImages(projectPath),
    enabled: !!projectPath,
  })

  const { data: annoData, isLoading: annoLoading } = useQuery({
    queryKey: ['annotations', projectPath, currentFile],
    queryFn: () => getAnnotations(projectPath, currentFile!),
    enabled: !!projectPath && !!currentFile,
  })

  const { data: classesData } = useQuery<ClassDef[]>({
    queryKey: ['classes', projectPath],
    queryFn: () => getClasses(projectPath),
    enabled: !!projectPath,
  })

  const saveMut = useMutation({
    mutationFn: () => saveProject(projectPath),
    onSuccess: () => setDirty(false),
  })

  const replaceMut = useMutation({
    mutationFn: (bxs: BoundingBox[]) => replaceAnnotations(projectPath, currentFile!, bxs),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['images', projectPath] })
      qc.invalidateQueries({ queryKey: ['classes', projectPath] })
      setDirty(true)
    },
  })

  const copyPrevMut = useMutation({
    mutationFn: () => copyFromPrev(projectPath, currentFile!),
    onSuccess: (data) => {
      pushUndo(boxes)
      setBoxesState(data.boxes)
      replaceMut.mutate(data.boxes)
      // Switch to select mode and select the last box so it's immediately editable
      if (data.boxes.length > 0) {
        setTool('select')
        setSelectedBoxId(data.boxes[data.boxes.length - 1].id)
      }
    },
  })

  useEffect(() => {
    if (images.length > 0 && !currentFile) setCurrentFile(images[0].filename)
  }, [images])

  useEffect(() => {
    if (annoData) {
      setBoxesState(annoData.boxes ?? [])
      setUndoStack([])
      setRedoStack([])
      setSelectedBoxId(null)
    }
  }, [annoData])

  const pushUndo = useCallback((prev: BoundingBox[]) => {
    setUndoStack(s => [...s.slice(-UNDO_LIMIT + 1), prev])
    setRedoStack([])
  }, [])

  const setBoxes = useCallback((newBoxes: BoundingBox[]) => {
    setBoxesState(prev => {
      pushUndo(prev)
      return newBoxes
    })
    replaceMut.mutate(newBoxes)
  }, [pushUndo, replaceMut])

  const undo = useCallback(() => {
    if (undoStack.length === 0) return
    const prev = undoStack[undoStack.length - 1]
    setUndoStack(s => s.slice(0, -1))
    setRedoStack(s => [...s, boxes])
    setBoxesState(prev)
    setSelectedBoxId(null)
    replaceMut.mutate(prev)
  }, [undoStack, boxes, replaceMut])

  const redo = useCallback(() => {
    if (redoStack.length === 0) return
    const next = redoStack[redoStack.length - 1]
    setRedoStack(s => s.slice(0, -1))
    setUndoStack(s => [...s, boxes])
    setBoxesState(next)
    setSelectedBoxId(null)
    replaceMut.mutate(next)
  }, [redoStack, boxes, replaceMut])

  const gotoImage = useCallback((direction: 'prev' | 'next') => {
    if (!currentFile || images.length === 0) return
    const idx = images.findIndex(i => i.filename === currentFile)
    const next = direction === 'next' ? idx + 1 : idx - 1
    if (next >= 0 && next < images.length) { setCurrentFile(images[next].filename); setZoom(1) }
  }, [currentFile, images])

  const deleteBox = useCallback((id: string) => {
    const next = boxes.filter(b => b.id !== id)
    setBoxes(next)
    setSelectedBoxId(s => s === id ? null : s)
  }, [boxes, setBoxes])

  const currentIndex = images.findIndex(i => i.filename === currentFile)
  const classes: ClassDef[] = classesData ?? info?.classes ?? []
  const annotatedCount = images.filter(i => i.box_count > 0).length

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.ctrlKey || e.metaKey) {
        if (e.key === 'z') { e.preventDefault(); undo() }
        if (e.key === 'y' || (e.shiftKey && e.key === 'z')) { e.preventDefault(); redo() }
        if (e.key === 's') { e.preventDefault(); saveMut.mutate() }
        return
      }
      if (e.key === 'v' || e.key === 'V') setTool('select')
      if (e.key === 'r' || e.key === 'R') setTool('draw')
      if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') gotoImage('prev')
      if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') gotoImage('next')
      if (e.key === '=' || e.key === '+') setZoom(z => Math.min(z * 1.2, 8))
      if (e.key === '-') setZoom(z => Math.max(z / 1.2, 0.1))
      if (e.key === 'f' || e.key === 'F') setZoom(1)
      if (e.key === '1') setZoom(1 / fitScale)
      if (e.key === 'c' || e.key === 'C') copyPrevMut.mutate()
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedBoxId) {
        deleteBox(selectedBoxId)
      }
      // Class shortcuts 1-9
      const n = parseInt(e.key)
      if (n >= 1 && n <= 9 && n - 1 < classes.length) setSelectedClass(n - 1)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [undo, redo, gotoImage, saveMut, selectedBoxId, deleteBox, classes])

  if (!projectPath) return <div className="p-6 text-red-400">No project path specified.</div>
  if (infoLoading) return <div className="flex-1 flex items-center justify-center bg-[#0f172a]"><Spinner size={32} /></div>

  return (
    <div className="flex flex-col h-screen bg-[#0f172a] overflow-hidden">
      <Toolbar
        tool={tool}
        onToolChange={setTool}
        canUndo={undoStack.length > 0}
        canRedo={redoStack.length > 0}
        onUndo={undo}
        onRedo={redo}
        onSave={() => saveMut.mutate()}
        onCopyPrev={() => copyPrevMut.mutate()}
        onPrev={() => gotoImage('prev')}
        onNext={() => gotoImage('next')}
        onExport={() => setExportOpen(true)}
        onTrain={() => setTrainOpen(true)}
        onDetect={() => nav('/detection')}
        onGoHome={() => nav('/')}
        saving={saveMut.isPending}
        imageName={currentFile}
        imageIndex={currentIndex}
        imageTotal={images.length}
        zoom={zoom}
        onZoomIn={() => setZoom(z => Math.min(z * 1.2, 8))}
        onZoomOut={() => setZoom(z => Math.max(z / 1.2, 0.1))}
        onZoomFit={() => setZoom(1)}
        onZoom1to1={() => setZoom(1 / fitScale)}
      />

      {/* Progress bar */}
      <div className="h-1 bg-[#1e293b] shrink-0">
        {images.length > 0 && (
          <div
            className="h-full bg-violet-700 transition-all"
            style={{ width: `${(annotatedCount / images.length) * 100}%` }}
          />
        )}
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Image list sidebar */}
        <ImageList
          images={images}
          current={currentFile}
          projectPath={projectPath}
          onSelect={f => { setCurrentFile(f); setSelectedBoxId(null) }}
        />

        {/* Canvas */}
        <div className="flex-1 flex flex-col overflow-hidden relative">
          {annoLoading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/30">
              <Spinner size={24} />
            </div>
          )}
          {currentFile ? (
            <AnnotationCanvas
              projectPath={projectPath}
              filename={currentFile}
              boxes={boxes}
              classes={classes}
              selectedClass={selectedClass}
              tool={tool}
              selectedBoxId={selectedBoxId}
              onSelectBox={setSelectedBoxId}
              onBoxesChange={setBoxes}
              onSelectClass={setSelectedClass}
              zoom={zoom}
              onZoomChange={setZoom}
              onFitScaleChange={setFitScale}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-[#475569] text-sm">
              Select an image from the sidebar
            </div>
          )}
        </div>

        {/* Class + Annotations sidebar */}
        <ClassSidebar
          classes={classes}
          boxes={boxes}
          selectedClass={selectedClass}
          projectPath={projectPath}
          onSelectClass={setSelectedClass}
          onSelectBox={setSelectedBoxId}
          onDeleteBox={deleteBox}
          selectedBoxId={selectedBoxId}
        />
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-4 px-4 h-7 bg-[#0f172a] border-t border-[#1e293b] shrink-0 text-[11px] text-[#64748b]">
        <span>Image: {currentFile ?? '—'}</span>
        <span className="text-[#334155]">|</span>
        <span>Boxes: {boxes.length}</span>
        <span className="text-[#334155]">|</span>
        <span>{annotatedCount} / {images.length} annotated</span>
        {dirty && <span className="text-amber-500">●  unsaved</span>}
        <div className="flex-1" />
        <span className="text-[#334155]">{info?.name}</span>
      </div>

      <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} projectPath={projectPath} />
      <TrainDialog open={trainOpen} onClose={() => setTrainOpen(false)} />
    </div>
  )
}
