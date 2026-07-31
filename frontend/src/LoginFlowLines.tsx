import { useEffect, useRef } from 'react'

type Point = { x: number; y: number }

type DanceGroup = {
  start: Point
  controlA: Point
  controlB: Point
  end: Point
  count: number
  spread: number
  phase: number
  speed: number
  colorOffset: number
}

const DANCE_GROUPS: DanceGroup[] = [
  {
    start: { x: -.08, y: .1 },
    controlA: { x: .24, y: .05 },
    controlB: { x: .63, y: .71 },
    end: { x: 1.08, y: .62 },
    count: 7,
    spread: .16,
    phase: .2,
    speed: .34,
    colorOffset: 0,
  },
  {
    start: { x: -.1, y: .73 },
    controlA: { x: .25, y: 1.02 },
    controlB: { x: .68, y: .28 },
    end: { x: 1.1, y: .22 },
    count: 6,
    spread: .15,
    phase: 2.2,
    speed: -.28,
    colorOffset: 1,
  },
  {
    start: { x: .12, y: 1.08 },
    controlA: { x: .06, y: .62 },
    controlB: { x: .96, y: .46 },
    end: { x: .88, y: -.1 },
    count: 5,
    spread: .12,
    phase: 4.2,
    speed: .24,
    colorOffset: 2,
  },
]

const LINE_PALETTE: Array<[number, number, number]> = [
  [94, 158, 255],
  [80, 190, 174],
  [238, 154, 92],
]

function lineColor(time: number, offset: number): [number, number, number] {
  const position = (time / 10 + offset) % LINE_PALETTE.length
  const currentIndex = Math.floor(position)
  const nextIndex = (currentIndex + 1) % LINE_PALETTE.length
  const progress = position - currentIndex
  const eased = progress * progress * (3 - 2 * progress)
  const current = LINE_PALETTE[currentIndex]
  const next = LINE_PALETTE[nextIndex]

  return current.map((channel, index) => (
    Math.round(channel + (next[index] - channel) * eased)
  )) as [number, number, number]
}

function traceDanceLine(
  context: CanvasRenderingContext2D,
  group: DanceGroup,
  width: number,
  height: number,
  time: number,
  lineOffset: number,
  pointerX: number,
  pointerY: number,
) {
  const phase = group.phase + time * group.speed + lineOffset * .1
  const directionX = group.end.x - group.start.x
  const directionY = group.end.y - group.start.y
  const directionLength = Math.max(Math.hypot(directionX, directionY), .001)
  const normalX = -directionY / directionLength
  const normalY = directionX / directionLength
  const offset = lineOffset * group.spread
  const primary = Math.sin(phase)
  const secondary = Math.cos(phase * .78 + group.phase * .35)
  const counter = Math.sin(phase * .91 + 1.7)
  const pointerShiftX = (pointerX - .5) * .035
  const pointerShiftY = (pointerY - .5) * .035

  const startX = group.start.x + normalX * offset * .45 + primary * .012
  const startY = group.start.y + normalY * offset * .45 + secondary * .014
  const controlAX = group.controlA.x + normalX * offset + primary * .075 + pointerShiftX
  const controlAY = group.controlA.y + normalY * offset + secondary * .095 + pointerShiftY * .45
  const controlBX = group.controlB.x + normalX * offset * .8 + secondary * .085 - pointerShiftX * .35
  const controlBY = group.controlB.y + normalY * offset * .8 + counter * .1 + pointerShiftY
  const endX = group.end.x + normalX * offset * .38 + counter * .014
  const endY = group.end.y + normalY * offset * .38 + primary * .016

  context.beginPath()
  context.moveTo(startX * width, startY * height)
  context.bezierCurveTo(
    controlAX * width,
    controlAY * height,
    controlBX * width,
    controlBY * height,
    endX * width,
    endY * height,
  )
}

function drawDancingLines(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  time: number,
  pointerX: number,
  pointerY: number,
) {
  context.clearRect(0, 0, width, height)
  context.lineCap = 'round'
  context.lineJoin = 'round'

  const compact = height < 360
  const scale = Math.max(.9, Math.min(1.2, Math.min(width / 760, height / 850)))

  DANCE_GROUPS.forEach((group) => {
    const lineCount = compact ? Math.max(3, group.count - 2) : group.count
    for (let index = 0; index < lineCount; index += 1) {
      const normalized = lineCount === 1 ? 0 : index / (lineCount - 1) * 2 - 1
      const centerWeight = 1 - Math.abs(normalized)
      const [red, green, blue] = lineColor(time, group.colorOffset + index * .1)

      traceDanceLine(context, group, width, height, time, normalized, pointerX, pointerY)
      context.strokeStyle = `rgba(${red}, ${green}, ${blue}, ${.07 + centerWeight * .2})`
      context.lineWidth = (.65 + centerWeight * 1.05) * scale
      context.stroke()
    }
  })
}

export function LoginFlowLines() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const pointerTarget = { x: .5, y: .5 }
    const pointer = { x: .5, y: .5 }
    let width = 1
    let height = 1
    let frameId = 0

    const render = (timestamp: number) => {
      pointer.x += (pointerTarget.x - pointer.x) * .022
      pointer.y += (pointerTarget.y - pointer.y) * .022
      drawDancingLines(context, width, height, reducedMotion.matches ? 0 : timestamp / 1000, pointer.x, pointer.y)
    }

    const animate = (timestamp: number) => {
      render(timestamp)
      frameId = window.requestAnimationFrame(animate)
    }

    const start = () => {
      window.cancelAnimationFrame(frameId)
      if (reducedMotion.matches || document.hidden) {
        render(0)
        return
      }
      frameId = window.requestAnimationFrame(animate)
    }

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const pixelRatio = Math.min(Math.max(window.devicePixelRatio || 1, 1.5), 2)
      width = Math.max(1, Math.round(rect.width))
      height = Math.max(1, Math.round(rect.height))
      canvas.width = Math.round(width * pixelRatio)
      canvas.height = Math.round(height * pixelRatio)
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
      render(performance.now())
    }

    const handlePointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      pointerTarget.x = Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(rect.width, 1)))
      pointerTarget.y = Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(rect.height, 1)))
    }

    const handleVisibilityChange = () => start()
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas)
    window.addEventListener('pointermove', handlePointerMove, { passive: true })
    document.addEventListener('visibilitychange', handleVisibilityChange)
    reducedMotion.addEventListener('change', start)
    resize()
    start()

    return () => {
      window.cancelAnimationFrame(frameId)
      resizeObserver.disconnect()
      window.removeEventListener('pointermove', handlePointerMove)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      reducedMotion.removeEventListener('change', start)
    }
  }, [])

  return <canvas ref={canvasRef} className="login-flow-lines" aria-hidden="true" />
}
