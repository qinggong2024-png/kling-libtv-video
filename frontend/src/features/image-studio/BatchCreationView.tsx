import { AlertTriangle, Check, Images, Package, Plus, Shirt, Sparkles, UserRound, WandSparkles } from 'lucide-react'
import { CustomPromptField } from '../../CustomPromptField'
import { MAX_IMAGE_CENTER_OUTFITS } from '../../imageCenterModel'
import type { ImageCenterDraft, ImageGenerationMode, ImageProvider, ImageTaskSummary, OutfitDraft } from '../../imageCenterModel'
import { OrderedAssetUpload, OutfitCard, OutfitNavItem } from './shared/ImageAssets'

export function BatchCreationView({ draft, summary, activeOutfit, activeOutfitIndex, generationStatusMessage, errors, updateDraft, updateConfig, selectMode, addOutfit, removeOutfit, setActiveOutfitId, updateOutfit, assetsOnly = false }: {
  assetsOnly?: boolean
  draft: ImageCenterDraft
  summary: ImageTaskSummary
  activeOutfit: OutfitDraft
  activeOutfitIndex: number
  generationStatusMessage: string
  errors: string[]
  updateDraft: (updater: (current: ImageCenterDraft) => ImageCenterDraft) => void
  updateConfig: (changes: Partial<ImageCenterDraft['config']>) => void
  selectMode: (mode: ImageGenerationMode) => void
  addOutfit: () => void
  removeOutfit: (id: string) => void
  setActiveOutfitId: (id: string) => void
  updateOutfit: (outfit: OutfitDraft) => void
}) {
  return <div className="image-center-create image-batch-workspace">
      <section className="image-center-section asset-composer" aria-labelledby="asset-composer-title">
        <div className="image-center-section__heading"><div><span className="section-number">01</span><div><h2 id="asset-composer-title">素材编排</h2><p>模特图片复用到全部套装，每套商品独立配置。</p></div></div><div className="asset-composer-toolbar"><span className="section-state"><Shirt size={15} />{summary.outfitCount}/{draft.outfits.length} 套已就绪</span>{!assetsOnly ? <a className="image-center-jump" href="#generation-config-title"><WandSparkles size={15} />生成配置</a> : null}</div></div>
        <div className="asset-composer-grid">
          <aside className="model-pack-column">
            <div className="asset-pack-heading"><span><UserRound size={18} /></span><div><h3>本批次模特</h3><p>正面必填，背面和侧面可选</p></div><i className={draft.model.front ? 'is-ready' : ''}>{draft.model.front ? '已就绪' : '待上传'}</i></div>
            <OrderedAssetUpload idPrefix="image-center-model" title="模特图片" description="按正面、背面、侧面排列；人物与环境作为参考" assets={draft.model} onChange={(model) => updateDraft((current) => ({ ...current, model }))} />
          </aside>
          <div className="outfit-pack-column" aria-labelledby="outfits-title">
            <div className="asset-pack-heading"><span><Package size={18} /></span><div><h3 id="outfits-title">产品套装</h3><p>每套正面必填，背面和侧面可选</p></div><div className="outfits-heading-actions"><strong>{draft.outfits.length}/{MAX_IMAGE_CENTER_OUTFITS}</strong><button type="button" className="primary-button outfit-add-button" disabled={draft.outfits.length >= MAX_IMAGE_CENTER_OUTFITS} onClick={addOutfit}><Plus size={16} />添加套装</button></div></div>
            <div className="outfit-workspace">
              <div className="outfit-navigator">
                <div className="outfit-navigator__head"><strong>套装列表</strong><span>{summary.outfitCount} 套已就绪</span></div>
                <div className="outfit-nav-list" role="tablist" aria-label="产品套装列表">{draft.outfits.map((outfit, index) => <OutfitNavItem key={outfit.id} outfit={outfit} index={index} selected={outfit.id === activeOutfit.id} canRemove={draft.outfits.length > 1} onSelect={() => setActiveOutfitId(outfit.id)} onRemove={() => removeOutfit(outfit.id)} />)}</div>
                {draft.outfits.length < MAX_IMAGE_CENTER_OUTFITS ? <button type="button" className="outfit-nav-add" onClick={addOutfit}><Plus size={15} />添加下一套</button> : null}
              </div>
              <div id="active-outfit-editor" className="active-outfit-editor" role="tabpanel" aria-labelledby={`outfit-tab-${activeOutfit.id}`}>
                <OutfitCard outfit={activeOutfit} index={activeOutfitIndex} onChange={updateOutfit} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {!assetsOnly ? <section className="image-center-section generation-config" aria-labelledby="generation-config-title">
        <div className="image-center-section__heading"><div><span className="section-number">02</span><div><h2 id="generation-config-title">生成配置</h2><p>统一配置会应用到全部已就绪套装。</p></div></div><span className="section-state"><WandSparkles size={15} />预计 {summary.totalImages} 张</span></div>
        <div className="image-config-grid">
          <fieldset className="image-config-block"><legend>生成引擎</legend><div className="image-provider-control">{(['gpt', 'nanobanana'] as ImageProvider[]).map((provider) => <button key={provider} type="button" className={draft.config.provider === provider ? 'is-selected' : ''} onClick={() => updateConfig({ provider })}><span>{provider === 'gpt' ? 'GPT Image 2' : 'Nano Banana 2'}</span><small>WaveSpeed API</small>{draft.config.provider === provider ? <Check size={14} /> : null}</button>)}</div></fieldset>
          <fieldset className="image-config-block image-config-select"><legend>画面比例</legend><select aria-label="画面比例" value={draft.config.aspectRatio} onChange={(event) => updateConfig({ aspectRatio: event.target.value })}><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option><option value="3:4">3:4</option><option value="4:3">4:3</option></select></fieldset>
          <fieldset className="image-config-block image-config-select"><legend>分辨率</legend><select aria-label="分辨率" value={draft.config.resolution} onChange={(event) => updateConfig({ resolution: event.target.value })}><option value="1k">1K</option><option value="2k">2K</option><option value="4k">4K</option></select></fieldset>
          <fieldset className="image-config-block"><legend>统一结果数量</legend><div className="image-result-count">{([1, 2, 3, 4] as const).map((count) => <button key={count} type="button" className={draft.config.resultCount === count ? 'is-selected' : ''} onClick={() => updateConfig({ resultCount: count })}>{count}</button>)}</div></fieldset>
        </div>
        <div className="image-prompt-grid" role="radiogroup" aria-label="生成任务">
          <section className={draft.config.modes.includes('fusion') ? 'is-selected' : 'is-disabled'}><header><button type="button" className="image-prompt-mode" role="radio" aria-checked={draft.config.modes.includes('fusion')} onClick={() => selectMode('fusion')}><span><Sparkles size={17} /></span><span><strong>多图融合</strong><small>按现有视角生成换装基准图</small></span><i>{draft.config.modes.includes('fusion') ? <Check size={14} /> : null}</i></button></header><CustomPromptField scope="image_fusion" label="自定义提示词" value={draft.config.fusionPrompt} disabled={!draft.config.modes.includes('fusion')} onChange={(fusionPrompt) => updateConfig({ fusionPrompt })} placeholder="描述人物一致性、服装还原和画面要求" /></section>
          <section className={draft.config.modes.includes('storyboard') ? 'is-selected' : 'is-disabled'}><header><button type="button" className="image-prompt-mode" role="radio" aria-checked={draft.config.modes.includes('storyboard')} onClick={() => selectMode('storyboard')}><span><Images size={17} /></span><span><strong>分镜图生成</strong><small>从一段提示词扩展有序镜头</small></span><i>{draft.config.modes.includes('storyboard') ? <Check size={14} /> : null}</i></button></header><CustomPromptField scope="image_storyboard" label="自定义提示词" value={draft.config.storyboardPrompt} disabled={!draft.config.modes.includes('storyboard')} onChange={(storyboardPrompt) => updateConfig({ storyboardPrompt })} placeholder="用一整段文字描述镜头顺序和展示重点" /></section>
        </div>
        <label className="back-inference-toggle"><input type="checkbox" checked={draft.config.allowBackInference} onChange={(event) => updateConfig({ allowBackInference: event.target.checked })} /><span><i>{draft.config.allowBackInference ? <Check size={13} /> : null}</i><strong>允许推测缺失的背面</strong><small>只有模特或产品一方提供背面时继续生成，并给结果添加风险标签。</small></span></label>
        <div className="image-generation-summary"><div><span><Shirt size={18} /></span><p><strong>{summary.outfitCount}</strong><small>就绪套装</small></p></div><div><span><Sparkles size={18} /></span><p><strong>{summary.fusionImages}</strong><small>融合结果</small></p></div><div><span><Images size={18} /></span><p><strong>{summary.storyboardImages}</strong><small>分镜结果</small></p></div><div className="is-total"><span><WandSparkles size={18} /></span><p><strong>{summary.totalImages}</strong><small>预计总图片</small></p></div><div className="image-generation-submit"><small>{summary.inferredBackOutfitCount ? `${summary.inferredBackOutfitCount} 套将推测背面` : '不会强制要求背面或侧面图'}</small><p className="image-generation-submit__hint" role="status">{generationStatusMessage}</p></div></div>
        {errors.length ? <div className="image-config-errors" role="alert"><AlertTriangle size={16} /><span>{errors[0]}</span></div> : null}
      </section> : null}
    </div>
}
