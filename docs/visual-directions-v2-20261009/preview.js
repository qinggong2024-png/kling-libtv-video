/* Local interaction model only. No API client, credentials or provider access. */
(() => {
  const app = document.getElementById('app')
  const direction = document.body.dataset.direction
  const icon = (name) => window.previewIcons[name] || ''
  const iconButton = (name, label, action, extra = '') =>
    `<button class="icon quiet" title="${label}" aria-label="${label}" ${action} ${extra}>${icon(name)}</button>`
  const navItems = [['Image', '图片中心'], ['Film', '视频制作'], ['ListTodo', '任务中心'], ['Folder', '内容库']]
  const nav = (mobile = false) => navItems.map(([name, label], index) =>
    `<button class="${index === 1 ? 'active' : ''}" ${index === 1 ? 'aria-current="page"' : ''} data-nav="${index}">${icon(name)}<span>${mobile ? ['图片', '视频', '任务', '素材'][index] : label}</span></button>`).join('')
  let count = 1
  let activeMode = 'automatic'
  let resultState = 'review'
  let restoreFocus
  let toastTimer
  const initialAssets = [
    { name: '穿搭参考 01', src: 'media/look-01.jpg' },
    { name: '穿搭参考 02', src: 'media/look-02.jpg' },
  ]
  let assets = [...initialAssets]
  const directions = [
    ['a', 'A 安静工作台', 'index.html'],
    ['b', 'B 工具面板', 'direction-b.html'],
    ['c', 'C 阶段流程', 'direction-c.html'],
  ]
  app.innerHTML = `
    <div class="proposal" role="note">
      <strong>第二轮设计</strong>
      <nav class="directions" aria-label="视觉方向">${directions.map(([key, name, href]) => `<a href="${href}" ${direction === key ? 'aria-current="page"' : ''}>${name}</a>`).join('')}</nav>
      <span class="safety">示例素材 · 无真实生成或扣费</span>
    </div>
    <div class="shell">
      <aside class="sidebar">
        <div class="brand"><span class="brand-symbol">${icon('Layers')}</span><div><strong>衣影工坊</strong><small>创意制作空间</small></div></div>
        <div><div class="nav-label">工作区</div><nav class="nav" aria-label="工作区">${nav()}</nav></div>
        <div class="sidebar-bottom"><nav class="nav" aria-label="支撑功能"><button data-support="管理中心">${icon('SlidersHorizontal')}管理中心</button><button data-support="偏好设置">${icon('Settings')}偏好设置</button></nav><div class="person"><span class="avatar">创</span><div><strong>创作人员</strong><small style="display:block">样稿身份</small></div></div></div>
      </aside>
      <main class="main">
        <header class="topbar"><div class="crumb">工作区 ${icon('ChevronRight')} <span>视频制作</span></div><div class="top-actions"><span class="muted">本地设计预览</span>${iconButton('Bell', '查看通知', 'data-notification')}</div></header>
        <div class="workspace">
          <div class="page-heading"><div><h1>视频制作</h1><p>从素材到镜头，专注每一次创作。</p></div><span class="draft">未提交</span></div>
          <div class="mode-tabs" role="tablist" aria-label="视频工作阶段"><button role="tab" aria-selected="true" id="prepare-tab" aria-controls="prepare-panel" data-stage="prepare">${icon('Clapperboard')}准备素材</button><button role="tab" aria-selected="false" tabindex="-1" id="result-tab" aria-controls="result-panel" data-stage="result">${icon('Play')}生成结果</button></div>
          <section id="prepare-panel" role="tabpanel" aria-labelledby="prepare-tab">
            <div class="preparation">
              <section class="asset-area" aria-labelledby="asset-heading"><div class="section-heading"><h2 id="asset-heading">素材准备</h2><small id="asset-count">2 张素材</small></div>
                <div class="asset-grid" id="asset-grid"></div>
                <button class="upload" id="upload">${icon('Plus')}添加参考图片</button>
                <input id="file-picker" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden>
                <details class="subject"><summary>人物一致性<span class="optional">可选</span>${icon('ChevronDown')}</summary><div class="subject-inner"><label for="subject-select" class="muted">人物参考</label><select id="subject-select"><option>不使用主体参考</option><option>样稿人物参考</option></select></div></details>
              </section>
              <section class="configuration" aria-labelledby="configuration-heading"><div class="section-heading"><h2 id="configuration-heading">生成配置</h2><small></small></div>
                <div class="field"><label for="template">视频模板</label><select id="template"><option>服装多镜头展示 · 样稿</option><option>服装细节展示 · 样稿</option></select><div class="template-meta"><span class="muted">竖屏 9:16 · 2–7 张参考图</span><button class="quiet" id="recipe">查看配方 ${icon('ArrowUpRight')}</button></div></div>
                <div class="field"><label>生成方式</label><div class="segmented" role="group" aria-label="生成方式"><button aria-pressed="true" data-mode="automatic">自动编排</button><button aria-pressed="false" data-mode="custom">自定义创意</button></div></div>
                <div class="field"><label for="intention">创作意图</label><textarea id="intention">突出服装轮廓与面料质感，镜头衔接自然，保留完整穿搭。</textarea></div>
                <details class="advanced"><summary>高级生成参数 ${icon('ChevronDown')}</summary><div class="field"><label for="motion">动作强度</label><select id="motion"><option>轻微动作</option><option selected>标准动作</option><option>明显动作</option></select></div><div class="field"><label for="cut">镜头衔接</label><select id="cut"><option>明确切镜</option><option>尽量连续</option></select></div></details>
              </section>
            </div>
            <div class="submission"><div><div class="submit-options"><div class="compact-field"><label for="duration">视频时长</label><select id="duration"><option>5 秒</option><option selected>10 秒</option></select></div><div class="compact-field"><span>生成数量</span><div class="stepper">${iconButton('Minus', '减少数量', 'id="decrease"')}<output id="quantity" aria-live="polite">1</output>${iconButton('Plus', '增加数量', 'id="increase"')}</div></div></div><label class="ack"><input type="checkbox" id="acknowledge"><span>我已确认素材与配置。正式提交会调用生成服务并可能产生费用。</span></label></div><button class="primary submit-button" id="submit" disabled>${icon('Sparkles')}生成视频</button></div>
            <div class="status-line" role="status" id="submission-status">${icon('Info')}<span>当前为视觉样稿，不会创建真实任务。</span></div>
          </section>
          <section class="results" id="result-panel" role="tabpanel" aria-labelledby="result-tab" hidden>
            <div class="results-heading"><div class="section-title"><h2>生成结果</h2><small>示例状态</small></div><div class="status-switch" role="group" aria-label="示例结果状态">${[['review','待审核'],['running','生成中'],['failed','失败'],['empty','空结果']].map(([state, name]) => `<button data-state="${state}" aria-pressed="${state === 'review'}">${name}</button>`).join('')}</div></div>
            <div class="result-content" id="result-content"></div>
          </section>
        </div>
      </main>
    </div>
    <nav class="mobile-nav" aria-label="移动工作区">${nav(true)}</nav>
    <dialog class="drawer" id="recipe-dialog" aria-labelledby="recipe-title"><div class="dialog-heading"><h2 id="recipe-title">服装展示配方</h2>${iconButton('X', '关闭配方', 'data-close')}</div><div class="dialog-content"><span class="badge">${icon('Info')}样稿配方 · 非服务端配置</span><dl><dt>素材</dt><dd>服装参考图 2–7 张</dd><dt>画面比例</dt><dd>9:16 竖屏</dd><dt>镜头</dt><dd>全身展示、侧身与面料细节</dd><dt>动作</dt><dd>缓慢侧身，停稳后保持服装完整可见</dd><dt>质量边界</dt><dd>生成完成不等于审核通过或可交付</dd></dl></div></dialog>
    <dialog id="image-dialog" aria-labelledby="image-title"><div class="dialog-heading"><h2 id="image-title">素材检查</h2>${iconButton('X', '关闭素材检查', 'data-close')}</div><div class="dialog-content"><img id="large-image" alt=""><p class="muted">样稿参考素材</p></div></dialog>
    <dialog class="drawer" id="review-dialog" aria-labelledby="review-title"><div class="dialog-heading"><h2 id="review-title">结果审核</h2>${iconButton('X', '关闭结果审核', 'data-close')}</div><div class="dialog-content"><span class="badge">${icon('ClipboardCheck')}待人工审核 · 示例</span><p>请分别检查服装一致性、画面完整性与镜头衔接。</p><div class="field"><label for="review-decision">审核意见</label><select id="review-decision"><option value="">请选择</option><option value="qualified">合格</option><option value="rejected">拒绝</option></select></div><div class="field"><label for="review-reason">审核说明</label><textarea id="review-reason" placeholder="拒绝时填写原因"></textarea></div><p id="review-error" role="alert"></p><button class="primary" id="review-save">预览保存反馈</button><p class="muted">仅预览反馈，不写入审核或交付状态。</p></div></dialog>
    <dialog id="notice-dialog" aria-labelledby="notice-title"><div class="dialog-heading"><h2 id="notice-title">预览通知</h2>${iconButton('X', '关闭通知', 'data-close')}</div><div class="dialog-content"><p>当前没有真实生产通知。</p><p class="muted">此页面仅展示设计方向与本地交互。</p></div></dialog>
    <div class="toast" id="toast" role="status" hidden></div>`

  function toast(text) {
    const el = document.getElementById('toast')
    el.textContent = text
    el.hidden = false
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => { el.hidden = true }, 2600)
  }
  function updateSubmit() {
    document.getElementById('submit').disabled = assets.length < 2 || !document.getElementById('acknowledge').checked
  }
  function renderAssets() {
    document.getElementById('asset-grid').innerHTML = assets.map((asset, index) => `
      <article class="asset"><button class="asset-image" data-preview="${index}" aria-label="放大检查参考图 ${index + 1}"><img src="${asset.src}" alt="服装穿搭参考图 ${index + 1}"><span class="asset-index">${String(index + 1).padStart(2, '0')}</span></button><div class="asset-footer"><strong>参考图 ${String(index + 1).padStart(2, '0')}</strong><div class="asset-tools">${iconButton('ArrowLeft', '向前移动参考图 ' + (index + 1), `data-move="${index}" data-delta="-1"`, index === 0 ? 'disabled' : '')}${iconButton('ArrowRight', '向后移动参考图 ' + (index + 1), `data-move="${index}" data-delta="1"`, index === assets.length - 1 ? 'disabled' : '')}${iconButton('Trash2', '删除参考图 ' + (index + 1), `data-remove="${index}"`)}</div></div></article>`).join('')
    document.getElementById('asset-count').textContent = `${assets.length} 张参考图`
    updateSubmit()
  }
  function showStage(stage) {
    document.querySelectorAll('[data-stage]').forEach(el => {
      const selected = el.dataset.stage === stage
      el.setAttribute('aria-selected', String(selected))
      el.tabIndex = selected ? 0 : -1
    })
    document.getElementById('prepare-panel').hidden = stage !== 'prepare'
    document.getElementById('result-panel').hidden = stage !== 'result'
  }
  function renderResult() {
    const content = document.getElementById('result-content')
    document.querySelectorAll('[data-state]').forEach(el => el.setAttribute('aria-pressed', String(el.dataset.state === resultState)))
    if (resultState === 'empty') {
      content.innerHTML = `<div class="empty">${icon('Film')}<h3>暂无生成结果</h3><p>当前示例任务还没有结果。</p><button data-prepare>返回素材准备</button></div>`
    } else if (resultState === 'failed') {
      content.innerHTML = `<div class="failure" role="alert"><h3>${icon('CircleAlert')}示例任务生成失败</h3><p>样稿错误：生成服务暂不可用。先查询提交状态，避免重复扣费。</p><button data-query>${icon('RefreshCw')}安全查询</button></div>`
    } else if (resultState === 'running') {
      content.innerHTML = `<div class="progress" role="status"><h3>正在生成 · 样稿状态</h3><div class="progress-track"><span></span></div><p>素材已准备，等待生成结果。这里没有实际 Provider 调用。</p></div>`
    } else {
      content.innerHTML = `<div class="result-poster"><img src="media/look-01.jpg" alt="样稿结果封面，非生成视频">${iconButton('Maximize2', '检查样稿封面', 'data-cover')}</div><div class="result-info"><span class="badge">${icon('ClipboardCheck')}待人工审核 · 示例</span><h3 style="margin-top:8px">服装展示 / 示例结果</h3><p>封面仅用于排版展示，不代表真实视频、审核通过或交付。</p><div class="result-actions"><button data-review>${icon('ClipboardCheck')}查看审核面板</button><button disabled title="没有真实视频文件">${icon('Download')}下载</button></div></div>`
    }
  }
  function openDialog(id) {
    restoreFocus = document.activeElement
    document.getElementById(id).showModal()
  }
  document.querySelectorAll('dialog').forEach(dialog => {
    dialog.addEventListener('close', () => restoreFocus?.focus())
    dialog.addEventListener('click', event => {
      if (event.target.closest('[data-close]')) dialog.close()
    })
  })
  document.getElementById('app').addEventListener('click', event => {
    const target = event.target.closest('button')
    if (!target) return
    if (target.hasAttribute('data-stage')) showStage(target.dataset.stage)
    if (target.hasAttribute('data-state')) { resultState = target.dataset.state; renderResult() }
    if (target.hasAttribute('data-mode')) {
      activeMode = target.dataset.mode
      document.querySelectorAll('[data-mode]').forEach(el => el.setAttribute('aria-pressed', String(el.dataset.mode === activeMode)))
      document.getElementById('intention').placeholder = activeMode === 'custom' ? '描述你希望的镜头、动作和商品重点' : ''
    }
    if (target.hasAttribute('data-preview') || target.hasAttribute('data-cover')) {
      const asset = target.hasAttribute('data-cover') ? initialAssets[0] : assets[Number(target.dataset.preview)]
      document.getElementById('large-image').src = asset.src
      document.getElementById('large-image').alt = asset.name
      openDialog('image-dialog')
    }
    if (target.hasAttribute('data-move')) {
      const index = Number(target.dataset.move)
      const next = index + Number(target.dataset.delta)
      const moved = assets.splice(index, 1)[0]
      assets.splice(next, 0, moved)
      renderAssets()
      document.querySelector(`[data-preview="${next}"]`).focus()
      toast(`参考图已移至第 ${next + 1} 位`)
    }
    if (target.hasAttribute('data-remove')) {
      const index = Number(target.dataset.remove)
      const [removed] = assets.splice(index, 1)
      if (removed.src.startsWith('blob:')) URL.revokeObjectURL(removed.src)
      renderAssets()
      const next = document.querySelector(`[data-preview="${Math.max(0, Math.min(index, assets.length - 1))}"]`)
      ;(next || document.getElementById('upload')).focus()
      toast('已从样稿移除参考图')
    }
    if (target.hasAttribute('data-nav') && target.dataset.nav !== '1') toast('当前仅开放视频制作方向样稿，其他工作区将在方向确认后实现')
    if (target.hasAttribute('data-support')) toast(`${target.dataset.support}保留为现有支撑功能，本轮未修改`)
    if (target.hasAttribute('data-notification')) openDialog('notice-dialog')
    if (target.hasAttribute('data-query')) toast('样稿查询完成：没有真实提交，不会自动重新生成')
    if (target.hasAttribute('data-prepare')) { showStage('prepare'); document.getElementById('prepare-tab').focus() }
    if (target.hasAttribute('data-review')) openDialog('review-dialog')
  })
  document.getElementById('review-save').addEventListener('click', () => {
    const decision = document.getElementById('review-decision')
    const reason = document.getElementById('review-reason')
    const error = document.getElementById('review-error')
    if (!decision.value || (decision.value === 'rejected' && !reason.value.trim())) {
      error.textContent = decision.value ? '请填写拒绝原因。' : '请选择审核意见。'
      ;(decision.value ? reason : decision).focus()
      return
    }
    error.textContent = ''
    document.getElementById('review-dialog').close()
    toast('保存反馈示例：未写入审核状态，不授权交付')
  })
  document.querySelector('.mode-tabs').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const stage = event.key === 'ArrowLeft' || event.key === 'Home' ? 'prepare' : 'result'
    showStage(stage)
    document.querySelector(`[data-stage="${stage}"]`).focus()
  })
  document.getElementById('recipe').addEventListener('click', () => openDialog('recipe-dialog'))
  document.getElementById('acknowledge').addEventListener('change', updateSubmit)
  const updateCount = (delta) => {
    count = Math.max(1, Math.min(4, count + delta))
    document.getElementById('quantity').textContent = String(count)
    document.getElementById('decrease').disabled = count === 1
    document.getElementById('increase').disabled = count === 4
  }
  document.getElementById('decrease').addEventListener('click', () => updateCount(-1))
  document.getElementById('increase').addEventListener('click', () => updateCount(1))
  document.getElementById('submit').addEventListener('click', () => {
    resultState = 'running'
    renderResult()
    showStage('result')
    document.getElementById('result-tab').focus()
    toast('提交反馈示例：未创建任务，未调用生成服务')
  })
  document.getElementById('upload').addEventListener('click', () => document.getElementById('file-picker').click())
  document.getElementById('file-picker').addEventListener('change', event => {
    const chosen = Array.from(event.target.files)
    const valid = chosen.filter(file => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && file.size <= 20 * 1024 * 1024)
    if (chosen.length !== valid.length) toast('仅接受 20MB 以内的 JPG、PNG 或 WebP 图片')
    else if (assets.length + valid.length > 7) toast('样稿最多保留 7 张参考图')
    assets.push(...valid.slice(0, 7 - assets.length).map(file => ({ name: file.name, src: URL.createObjectURL(file) })))
    renderAssets()
    event.target.value = ''
  })
  renderAssets()
  renderResult()
  updateCount(0)
})()
