/* Second exploration: rearrange presentation, retaining local-only interaction. */
(() => {
  const direction = document.body.dataset.direction
  const icon = name => window.previewIcons[name] || ''
  const prep = document.querySelector('.preparation')
  const assets = document.querySelector('.asset-area')
  const config = document.querySelector('.configuration')
  const title = document.querySelector('.page-heading')
  document.querySelector('.brand-symbol').innerHTML = '衣'
  document.querySelector('.topbar .crumb').innerHTML = '衣影工坊 <span>/</span> 视频工作区'
  document.querySelector('.top-actions .muted').textContent = '设计预览'
  document.querySelector('.sidebar .nav-label').textContent = '制作'
  document.querySelector('.page-heading .draft').innerHTML = `${icon('Clapperboard')}草稿`
  document.querySelector('.field > label[for="template"]').textContent = '制作模板'
  document.querySelector('.upload').innerHTML = `${icon('Plus')}添加素材 <span>JPG / PNG / WebP</span>`
  document.querySelector('.configuration .section-heading small').remove()
  document.querySelector('.configuration h2').textContent = '镜头与创意'
  const hint = document.createElement('p')
  hint.className = 'asset-hint'
  hint.textContent = '按镜头顺序整理，点击图片检查细节。'
  assets.querySelector('.section-heading').after(hint)
  document.querySelector('.template-meta .muted').textContent = '9:16 · 2–7 张素材'
  const prompt = document.querySelector('#intention')
  prompt.value = '自然转身，展示服装的廓形与面料。\n保持完整穿搭，镜头轻柔衔接。'
  const promptShell = document.createElement('div')
  promptShell.className = 'prompt-shell'
  prompt.replaceWith(promptShell)
  promptShell.append(prompt)
  const promptFooter = document.createElement('div')
  promptFooter.className = 'prompt-footer'
  promptFooter.innerHTML = `${icon('Sparkles')}创意会与模板共同编排`
  promptShell.append(promptFooter)
  document.querySelector('.status-line span').textContent = '本地交互样稿，不创建任务或扣费。'
  if (direction === 'b') {
    title.querySelector('p').textContent = '素材在左，创意在右。必要设置，触手可及。'
    config.classList.add('inspector')
    config.querySelector('.section-heading h2').textContent = '制作设置'
    assets.querySelector('h2').textContent = '镜头素材'
    const mode = config.querySelector('[data-mode]').closest('.field')
    mode.classList.add('mode-field')
    const template = config.querySelector('#template').closest('.field')
    template.before(mode)
  }
  if (direction === 'c') {
    title.querySelector('p').textContent = '先准备好素材，再确定这支视频的表达。'
    const steps = document.createElement('nav')
    steps.className = 'workflow-steps'
    steps.setAttribute('aria-label', '制作步骤')
    steps.innerHTML = '<button data-step="assets" aria-current="step"><span>1</span>整理素材</button><i></i><button data-step="creative"><span>2</span>设定创意</button><i></i><button data-step="confirm"><span>3</span>确认生成</button>'
    document.querySelector('.mode-tabs').after(steps)
    document.body.dataset.step = 'assets'
    const next = document.createElement('button')
    next.className = 'primary next-step'
    next.innerHTML = `继续设定创意 ${icon('ArrowRight')}`
    next.type = 'button'
    assets.append(next)
    const back = document.createElement('button')
    back.className = 'quiet back-step'
    back.innerHTML = `${icon('ArrowLeft')}返回素材`
    config.append(back)
    function showStep(step) {
      document.body.dataset.step = step
      steps.querySelectorAll('button').forEach(button => {
        if (button.dataset.step === step) button.setAttribute('aria-current', 'step')
        else button.removeAttribute('aria-current')
      })
      if (step === 'creative') prompt.focus()
      if (step === 'confirm') document.querySelector('#acknowledge').focus()
    }
    next.addEventListener('click', () => showStep('creative'))
    back.addEventListener('click', () => { showStep('assets'); next.focus() })
    steps.addEventListener('click', event => {
      const button = event.target.closest('button')
      if (button) showStep(button.dataset.step)
    })
    const confirm = document.createElement('button')
    confirm.className = 'primary next-step'
    confirm.innerHTML = `确认生成设置 ${icon('ArrowRight')}`
    config.append(confirm)
    confirm.addEventListener('click', () => showStep('confirm'))
    /* Actual generation gate still checks assets and explicit acknowledgement. */
  }
  document.querySelector('.ack span').textContent = '样稿确认：仅预览交互，未授权真实付费生成。'
})()
