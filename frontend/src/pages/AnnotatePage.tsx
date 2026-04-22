import { useState, useCallback, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getProjectInfo, getProjectImages, getAnnotations,
  replaceAnnotations, saveProject, copyFromPrev,
} from '../lib/api'
import type { BoundingBox, ClassDef, ImageEntry, ProjectInfo } from '../lib/types'
import { ImageList } from '../components/annotate/ImageList'
import { AnnotationCanvas } from '../components/annotate/AnnotationCanvas'
import { ClassSidebar } from '../components/annotate/ClassSidebar'
import { Toolbar } from '../components/annotate/Toolbar'
import { ExportDialog } from '../components/annotate/ExportDialog'
import { TrainDialog } from '../components/annotate/TrainDialog'
import { Spinner } from '../components/ui/Spinner'
import { Button } from '../components/ui/Button'

const UNDO_LIMIT = 50

export function AnnotatePage() {
  const [params] = useSearchParams()
  const projectPath = params.get('project') ?? ''
  const nav = useNavigate()
  const qc = useQueryClient()

  const [currentFile, setCurrentFile] = useState<string | null>(null)
  const [tool, setTool] = useState<'draw' | 'select'>('draw')
  const [selectedClass, setSelectedClass] = useState(0)
  const [boxes, setBoxesState] = useState<BoundingBox[]>([])
  const [undoStack, setUndoStack] = useState<BoundingBox[][]>([])
  const [redoStack, setRedoStack] = useState<BoundingBox[][]>([])
  const [exportOpen, setExportOpen] = useState(false)
  const [trainOpen, setTrainOpen] = useState(false)
  const [dirty, setDirty] = useState(false)

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

  const saveMut = useMutation({
    mutationFn: () => saveProject(projectPath),
    onSuccess: () => setDirty(false),
  })

  const replaceMut = useMutation({
    mutationFn: (bxs: BoundingBox[]) => replaceAnnotations({ path: projectPath, filename: currentFile, boxes: bxs }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['images', projectPath] })
      setDirty(true)
    },
  })

  const copyPrevMut = useMutation({
    mutationFn: () => copyFromPrev(projectPath, currentFile!),
    onSuccess: (data) => {
      pushUndo(boxes)
      setBoxesState(data.boxes)
      replaceMut.mutate(data.boxes)
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

  const undo = () => {
    if (undoStack.length === 0) return
    const prev = undoStack[undoStack.length - 1]
    setUndoStack(s => s.slice(0, -1))
    setRedoStack(s => [...s, boxes])
    setBoxesState(prev)
    replaceMut.mutate(prev)
  }

  const redo = () => {
    if (redoStack.length === 0) return
    const next = redoStack[redoStack.length - 1]
    setRedoStack(s => s.slice(0, -1))
    setUndoStack(s => [...s, boxes])
    setBoxesState(next)
    replaceMut.mutate(next)
  }

  const gotoImage = (direction: 'prev' | 'next') => {
    if (!currentFile || images.length === 0) return
    const idx = images.findIndex(i => i.filename === currentFile)
    const next = direction === 'next' ? idx + 1 : idx - 1
    if (next >= 0 && next < images.length) setCurrentFile(images[next].filename)
  }

  const currentIndex = images.findIndex(i => i.filename === currentFile)
  const classes: ClassDef[] = info?.classes ?? []

  // Keyboard shortcuts
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
      if (e.key === 'd' || e.key === 'D') setTool('draw')
      if (e.key === 'ArrowLeft' || e.key === 'a') gotoImage('prev')
      if (e.key === 'ArrowRight') gotoImage('next')
      if (e.key === 'c' || e.key === 'C') copyPrevMut.mutate()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [undo, redo, gotoImage, saveMut])

  if (!projectPath) return <div className="p-6 text-red-400">No project path specified.</div>
  if (infoLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32} /></div>

  return (
    <div className="flex flex-col h-screen bg-[#0f0d14] overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-[#17152a] border-b border-slate-800 shrink-0">
        <Button variant="ghost" size="sm" onClick={() => nav('/')}>← Back</Button>
        <span className="text-sm font-semibold text-slate-200">{info?.name}</span>
        {dirty && <span className="text-xs text-amber-400">● unsaved</span>}
        <div className="flex-1" />
        <span className="text-xs text-slate-600">{projectPath}</span>
      </div>

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
        saving={saveMut.isPending}
        imageName={currentFile}
        imageIndex={currentIndex}
        imageTotal={images.length}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Image list sidebar */}
        <div className="w-52 shrink-0 overflow-hidden">
          <ImageList
            images={images}
            current={currentFile}
            projectPath={projectPath}
            onSelect={setCurrentFile}
          />
        </div>

        {/* Canvas */}
        <div className="flex-1 flex overflow-hidden relative">
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
              onBoxesChange={setBoxes}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-600 text-sm">
              Select an image from the sidebar
            </div>
          )}
        </div>

        {/* Class sidebar */}
        <div className="w-44 shrink-0 overflow-hidden">
          <ClassSidebar
            classes={classes}
            boxes={boxes}
            selectedClass={selectedClass}
            projectPath={projectPath}
            onSelectClass={setSelectedClass}
          />
        </div>
      </div>

      <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} projectPath={projectPath} />
      <TrainDialog open={trainOpen} onClose={() => setTrainOpen(false)} />
    </div>
  )
}
