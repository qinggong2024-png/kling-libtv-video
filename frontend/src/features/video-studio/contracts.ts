import type { ComponentProps } from 'react'
import type { ProductionComposer } from '../production/ProductionComposer'

// Infer the legacy contract so both entries follow the same props definition.
export type VideoStudioProps = ComponentProps<typeof ProductionComposer>
