import { Camera, Compass, Map, Route } from 'lucide-react'
import type { DirectorSpatialPlan, KeyVisualDecision } from './spatialPlanning'
import { setKeyVisualDecision } from './spatialPlanning'

interface SpatialPlanningViewProps {
  plan: DirectorSpatialPlan
  onChange: (plan: DirectorSpatialPlan) => void
}

const decisionLabels: Record<KeyVisualDecision, string> = {
  keep: '纳入计划',
  optional: '可选',
  merge: '合并到前一帧',
}

export function SpatialPlanningView({ plan, onChange }: SpatialPlanningViewProps) {
  const { sceneFloorPlan: scene, cameraBlocking: camera, keyVisualPlan: keyVisuals } = plan
  return <section className="director-spatial" aria-label="空间与关键视觉规划">
    <div className="director-spatial__header">
      <div>
        <span className="director-panel__index">03</span>
        <div>
          <h3>Spatial Director</h3>
          <p>把场景平面、机位轴线和人物轨迹先锁成一份可追踪的规划证据。</p>
        </div>
      </div>
      <span className="director-state">{plan.status === 'planned_not_verified' ? '规划未验证' : plan.status}</span>
    </div>

    <div className="director-spatial__grid">
      <section className="director-spatial__section">
        <div className="director-spatial__section-heading"><Map size={16} /><strong>场景 Floor Plan</strong><span>{scene.sceneId} · {scene.layoutRevision}</span></div>
        <p className="director-spatial__lead">{scene.roomLabel} · {scene.status === 'planned_not_verified' ? '提案布局，未量测' : scene.status}</p>
        <dl className="director-spatial__facts">
          <div><dt>空间基准</dt><dd>{scene.origin}</dd></div>
          <div><dt>可达路线</dt><dd>{scene.walkableRoute}</dd></div>
          <div><dt>世界光源</dt><dd>{scene.lightWorldDirection}</dd></div>
        </dl>
        <div className="director-anchor-list">
          {scene.anchors.map((anchor) => <span key={anchor.id}><b>{anchor.id}</b>{anchor.object} · {anchor.zone}</span>)}
        </div>
      </section>

      <section className="director-spatial__section">
        <div className="director-spatial__section-heading"><Compass size={16} /><strong>机位与 180° 轴线</strong><span>{camera.crossing === 'none' ? '未越轴' : camera.crossing}</span></div>
        <p className="director-spatial__lead">{camera.actionAxis} · {camera.directionOfMovement}</p>
        <div className="director-camera-list">
          {camera.positions.map((position) => <article key={position.cameraId} className="director-camera-row">
            <b>{position.cameraId}</b>
            <div><strong>{position.worldZone}</strong><span>{position.worldHeading} · {position.lens}</span><small>{position.transition} · {position.axisSide} · {position.screenRelation}</small></div>
          </article>)}
        </div>
        <p className="director-spatial__note">世界左/右、camera-left 和 screen-left 分开记录；机位移动需要真实可达路径或剪辑说明。</p>
      </section>

      <section className="director-spatial__section director-spatial__section--wide">
        <div className="director-spatial__section-heading"><Route size={16} /><strong>人物运动轨迹</strong><span>{plan.actorBlocking.length} 个镜头</span></div>
        <div className="director-actor-timeline">
          {plan.actorBlocking.map((blocking) => <article key={blocking.shotId} className="director-actor-row">
            <b>{blocking.shotId}</b>
            <div><strong>{blocking.pathType} · {blocking.movementPath.join(' → ')}</strong><span>起点：{blocking.start.worldZone} · 终点：{blocking.end.worldZone}</span><small>{blocking.contactTransition}</small></div>
          </article>)}
        </div>
        <p className="director-spatial__note">支撑点随动作变化记录。规划层只说明物理连续性，未访问真实成图时不会标记 `visually_checked`。</p>
      </section>

      <section className="director-spatial__section director-spatial__section--wide director-key-visuals">
        <div className="director-spatial__section-heading"><Camera size={16} /><strong>Key Visual Shot Selector</strong><span>先完整时间线，再选最少充分关键图</span></div>
        <div className="director-key-visuals__counts" aria-label="关键视觉计数">
          <div><strong>{keyVisuals.shotCount}</strong><span>镜头</span></div>
          <div><strong>{keyVisuals.keyVisualCount}</strong><span>关键视觉</span></div>
          <div><strong>{keyVisuals.plannedImageCount}</strong><span>计划图片</span></div>
          <div><strong>{keyVisuals.authorizedImageCount}</strong><span>已授权</span></div>
          <div><strong>{keyVisuals.generatedImageCount}</strong><span>已生成</span></div>
        </div>
        <div className="director-key-visual-list">
          {keyVisuals.frames.map((frame) => <article key={frame.keyId} className={`director-key-visual${frame.decision === 'merge' ? ' is-merged' : ''}`}>
            <div className="director-key-visual__topline"><b>{frame.keyId}</b><span>{frame.shotIds.join(' · ')} · {frame.trigger}</span><em>{decisionLabels[frame.decision]}</em></div>
            <div className="director-key-visual__body">
              <div><strong>{frame.framing}</strong><p>{frame.reason}</p></div>
              <dl><div><dt>机位</dt><dd>{frame.cameraId}</dd></div><div><dt>人物状态</dt><dd>{frame.subjectWorldState}</dd></div><div><dt>商品展示</dt><dd>{frame.productVisibility}</dd></div></dl>
            </div>
            <div className="director-key-visual__actions">
              <button type="button" className={frame.decision === 'keep' ? 'is-selected' : ''} onClick={() => onChange(setKeyVisualDecision(plan, frame.keyId, 'keep'))}>纳入计划</button>
              <button type="button" className={frame.decision === 'optional' ? 'is-selected' : ''} onClick={() => onChange(setKeyVisualDecision(plan, frame.keyId, 'optional'))}>保留为可选</button>
              <button type="button" className={frame.decision === 'merge' ? 'is-selected' : ''} onClick={() => onChange(setKeyVisualDecision(plan, frame.keyId, 'merge'))}>合并前一帧</button>
            </div>
          </article>)}
        </div>
        <p className="director-spatial__note">当前为 `planned_not_rendered`。选择关键视觉不会授权图片生成，也不会把文字分镜升级为 `IMAGE_READY`。</p>
      </section>
    </div>
  </section>
}
