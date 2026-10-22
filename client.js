window.__ModuleLoader__.load({
  id: 'dsh-luoyu',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const endpoint = '/luoyu'
    const NS = 'settings.luoyu'
    const stylesId = 'dsh-luoyu-settings-styles'
    const css = `
      .luoyu{--ai-accent:var(--dsw-alias-brand-primary,#6c62da);--ai-text:var(--dsw-alias-label-primary,#20202a);--ai-muted:var(--dsw-alias-label-secondary,#646473);--ai-subtle:var(--dsw-alias-label-tertiary,#858593);--ai-border:var(--dsw-alias-border-l3,#dedee5);--ai-card:var(--dsw-alias-settings-card-fill,var(--dsw-alias-bg-layer-2,#fff));display:grid;gap:18px;width:min(100%,920px);padding:8px 0 30px;color:var(--ai-text);font:inherit}
      .luoyu *{box-sizing:border-box}.luoyu__hero{position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:26px 28px;border:1px solid var(--ai-border);border-radius:20px;background:radial-gradient(ellipse at 88% 15%,color-mix(in srgb,var(--ai-accent) 19%,transparent),transparent 42%),var(--ai-card)}
      .luoyu__hero-copy{display:flex;align-items:center;gap:17px;min-width:0}.luoyu__mark{display:grid;place-items:center;flex:0 0 54px;width:54px;height:54px;border-radius:17px;color:white;background:linear-gradient(145deg,var(--ai-accent),color-mix(in srgb,var(--ai-accent) 67%,#f18ca7));box-shadow:0 8px 22px color-mix(in srgb,var(--ai-accent) 24%,transparent)}
      .luoyu__eyebrow{margin:0 0 5px;color:var(--ai-accent);font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}.luoyu__title{margin:0;font-size:22px;font-weight:650;letter-spacing:-.025em;line-height:1.25}.luoyu__lead{max-width:560px;margin:7px 0 0;color:var(--ai-muted);font-size:13px;line-height:1.55}.luoyu__profile{display:flex;align-items:center;gap:8px;flex:0 0 auto;padding:8px 11px;border:1px solid var(--ai-border);border-radius:999px;color:var(--ai-muted);font-size:12px;background:color-mix(in srgb,var(--ai-card) 78%,transparent)}
      .luoyu__grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(250px,.8fr);gap:16px;align-items:stretch}.luoyu__panel{min-width:0;padding:20px;border:1px solid var(--ai-border);border-radius:16px;background:var(--ai-card);box-shadow:0 2px 10px color-mix(in srgb,var(--ai-text) 3%,transparent)}.luoyu__panel--wide{grid-column:1/-1}.luoyu__panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:17px}.luoyu__heading{display:flex;align-items:center;gap:11px}.luoyu__icon{display:grid;place-items:center;width:36px;height:36px;flex:0 0 36px;border-radius:11px;color:var(--ai-accent);background:color-mix(in srgb,var(--ai-accent) 11%,transparent)}.luoyu__panel-title{margin:0;font-size:14px;font-weight:650;line-height:1.3}.luoyu__panel-hint{margin:4px 0 0;color:var(--ai-subtle);font-size:12px;line-height:1.45}
      .luoyu__badge{display:inline-flex;align-items:center;gap:7px;white-space:nowrap;padding:6px 9px;border:1px solid var(--ai-border);border-radius:999px;color:var(--ai-muted);font-size:11px;font-weight:600}.luoyu__dot{width:7px;height:7px;border-radius:50%;background:var(--ai-subtle)}.luoyu__badge--online{color:var(--dsw-alias-state-success-primary,#27885b);border-color:color-mix(in srgb,var(--dsw-alias-state-success-primary,#27885b) 28%,transparent);background:color-mix(in srgb,var(--dsw-alias-state-success-primary,#27885b) 8%,transparent)}.luoyu__badge--online .luoyu__dot{background:var(--dsw-alias-state-success-primary,#27885b);box-shadow:0 0 0 3px color-mix(in srgb,var(--dsw-alias-state-success-primary,#27885b) 16%,transparent)}.luoyu__badge--pending .luoyu__dot{background:var(--dsw-alias-state-warning-primary,#d49a32)}
      .luoyu__facts{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0 0 16px}.luoyu__fact{min-width:0;padding:11px 12px;border:1px solid var(--ai-border);border-radius:11px;background:color-mix(in srgb,var(--ai-card) 78%,var(--ai-text) 2%)}.luoyu__fact-label{display:block;margin-bottom:5px;color:var(--ai-subtle);font-size:10px;font-weight:650;letter-spacing:.06em;text-transform:uppercase}.luoyu__fact-value{display:block;overflow:hidden;color:var(--ai-text);font-size:12px;font-weight:550;text-overflow:ellipsis;white-space:nowrap}
      .luoyu__actions{display:flex;flex-wrap:wrap;gap:8px}.luoyu__button{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:36px;padding:8px 12px;border:1px solid var(--ai-border);border-radius:10px;color:var(--ai-text);background:transparent;font:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:background .15s,border-color .15s,transform .15s}.luoyu__button:hover:not(:disabled){border-color:color-mix(in srgb,var(--ai-accent) 45%,var(--ai-border));background:color-mix(in srgb,var(--ai-accent) 7%,transparent);transform:translateY(-1px)}.luoyu__button:focus-visible,.luoyu__input:focus-visible{outline:2px solid var(--ai-accent);outline-offset:2px}.luoyu__button:disabled{cursor:not-allowed;opacity:.48}.luoyu__button--primary{border-color:var(--ai-accent);color:var(--dsw-alias-label-primary-foreground,#fff);background:var(--dsw-alias-button-primary-fill,var(--ai-accent))}.luoyu__button--primary:hover:not(:disabled){background:var(--dsw-alias-button-primary-hover,var(--ai-accent));transform:translateY(-1px)}.luoyu__button--danger:hover:not(:disabled){color:var(--dsw-alias-state-error-primary,#c33);border-color:var(--dsw-alias-state-error-primary,#c33);background:color-mix(in srgb,var(--dsw-alias-state-error-primary,#c33) 7%,transparent)}
      .luoyu__qr{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:210px;padding:14px;border:1px dashed var(--ai-border);border-radius:13px;text-align:center;background:color-mix(in srgb,var(--ai-card) 82%,var(--ai-text) 2%)}.luoyu__qr img{display:block;width:min(100%,172px);height:auto;aspect-ratio:1;object-fit:contain;padding:7px;border:1px solid var(--ai-border);border-radius:12px;background:#fff}.luoyu__qr-title{margin:11px 0 4px;font-size:12px;font-weight:650}.luoyu__qr-copy{max-width:230px;margin:0;color:var(--ai-subtle);font-size:11px;line-height:1.5}.luoyu__qr-placeholder{display:grid;place-items:center;width:88px;height:88px;border-radius:22px;color:var(--ai-accent);background:color-mix(in srgb,var(--ai-accent) 9%,transparent)}
      .luoyu__field{display:grid;gap:7px;margin:0 0 15px}.luoyu__field-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.luoyu__label{color:var(--ai-text);font-size:12px;font-weight:650}.luoyu__help{color:var(--ai-subtle);font-size:11px;line-height:1.45}.luoyu__input{width:100%;min-height:39px;padding:9px 11px;border:1px solid var(--ai-border);border-radius:10px;color:var(--ai-text);background:var(--dsw-alias-bg-layer-1,transparent);font:inherit;font-size:12px;transition:border-color .15s,box-shadow .15s}.luoyu__input:focus{border-color:var(--ai-accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--ai-accent) 13%,transparent);outline:none}.luoyu__textarea{min-height:160px;resize:vertical;line-height:1.6}.luoyu__toggle-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 0;border-top:1px solid var(--ai-border)}.luoyu__toggle-copy{display:grid;gap:3px}.luoyu__check{width:17px;height:17px;accent-color:var(--ai-accent)}.luoyu__save-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:13px;border-top:1px solid var(--ai-border)}.luoyu__save-note{color:var(--ai-subtle);font-size:11px;line-height:1.4}.luoyu__notice{padding:10px 12px;border:1px solid color-mix(in srgb,var(--dsw-alias-state-success-primary,#27885b) 24%,transparent);border-radius:10px;color:var(--dsw-alias-state-success-primary,#27885b);background:color-mix(in srgb,var(--dsw-alias-state-success-primary,#27885b) 7%,transparent);font-size:12px}.luoyu__error{padding:10px 12px;border:1px solid color-mix(in srgb,var(--dsw-alias-state-error-primary,#c33) 25%,transparent);border-radius:10px;color:var(--dsw-alias-state-error-primary,#c33);background:color-mix(in srgb,var(--dsw-alias-state-error-primary,#c33) 7%,transparent);font-size:12px}.luoyu__footer{display:flex;align-items:center;gap:7px;padding:0 2px;color:var(--ai-subtle);font-size:11px}
      @media(max-width:680px){.luoyu__hero{align-items:flex-start;padding:20px}.luoyu__profile{display:none}.luoyu__grid{grid-template-columns:1fr}.luoyu__panel--wide{grid-column:auto}.luoyu__panel{padding:16px}.luoyu__facts{grid-template-columns:1fr 1fr}.luoyu__save-row{align-items:flex-start;flex-direction:column}.luoyu__save-row .luoyu__button{width:100%}}
    `
    const en = {
      nav: 'Luoyu', eyebrow: 'YOUR PERSONAL QQ COMPANION', title: 'Make your QQ companion yours', description: 'Connect your QQ account, choose a private workspace, and shape how your companion speaks.',
      connection: 'QQ connection', connectionHint: 'NapCat signs in as your own QQ account.', account: 'QQ account', transport: 'OneBot connection', unknown: 'Not signed in', connected: 'Connected', disconnected: 'Disconnected',
      online: 'Online', starting: 'Starting', stopped: 'Stopped', needsLogin: 'Login needed', unavailable: 'Unavailable', loading: 'Checking…',
      start: 'Start NapCat', stop: 'Stop NapCat', refreshQr: 'Refresh QR', qrTitle: 'Scan with QQ', qrHint: 'Open QQ on your phone and scan this code to sign in.', qrWaiting: 'Your login code will appear here after NapCat starts.',
      workspace: 'AI workspace', workspaceHint: 'Each QQ chat gets its own DSH session. Memories stay in this folder.', workspacePath: 'Workspace folder', workspaceHelp: 'An absolute folder path for this companion’s memories and files.',
      persona: 'Persona', personaHelp: 'Set the companion’s voice, identity, and conversation style.', privateReply: 'Reply to private messages', privateReplyHelp: 'Allow the companion to answer direct messages.', groupReply: 'Group chat replies', groupReplyHelp: 'Balanced mode waits for an active chat and follows the original 90–300 second reply interval. Direct mentions and replies to the bot are immediate.', balanced: 'Balanced participation', mention: 'Only when mentioned',
      save: 'Save changes', saving: 'Saving…', saved: 'Settings saved to this DSH profile.', workspaceChanged: 'Workspace updated. New chats will use fresh sessions; existing sessions remain in DSH.', saveHint: 'Changes are stored in this DSH profile.', loadingSettings: 'Loading your settings…',
      requestSent: 'NapCat request sent.', stoppedNotice: 'NapCat stopped.', profile: 'DSH PROFILE', ready: 'QQ is connected', noConnection: 'QQ is not connected yet', statusUnavailable: 'Could not load the connection status.',
    }
    const zh = {
      nav: 'Luoyu', eyebrow: '你的专属 QQ AI 伴侣', title: '打造属于你的 QQ 伴侣', description: '登录自己的 QQ，选择专属记忆目录，并定义 AI 伴侣的交流方式。',
      connection: 'QQ 连接', connectionHint: 'NapCat 将以你的 QQ 账号登录。', account: 'QQ 账号', transport: 'OneBot 连接', unknown: '尚未登录', connected: '已连接', disconnected: '未连接',
      online: '已连接', starting: '正在启动', stopped: '已停止', needsLogin: '等待登录', unavailable: '不可用', loading: '正在检查…',
      start: '启动 NapCat', stop: '停止 NapCat', refreshQr: '刷新二维码', qrTitle: '使用 QQ 扫码', qrHint: '打开手机 QQ，扫描二维码完成登录。', qrWaiting: '启动 NapCat 后，登录二维码会显示在这里。',
      workspace: 'AI 工作区', workspaceHint: '每个 QQ 聊天都会使用独立 DSH 会话，记忆保存在此目录。', workspacePath: '工作区目录', workspaceHelp: '用于保存这位 AI 伴侣的记忆和文件的绝对路径。',
      persona: 'AI 人设', personaHelp: '描述 AI 的身份、语气和交流风格。', privateReply: '回复私聊消息', privateReplyHelp: '私聊消息仍会像原版一样立即回复。', groupReply: '群聊回复频率', groupReplyHelp: '适度模式参考旧版 90–300 秒动态间隔；活跃群聊更频繁。@机器人或回复机器人消息时立即响应。', balanced: '适度参与', mention: '仅在被提及时回复',
      save: '保存更改', saving: '正在保存…', saved: '设置已保存到当前 DSH 配置。', workspaceChanged: '工作区已更新。新聊天将使用新会话，旧会话仍保留在 DSH 中。', saveHint: '更改会保存到当前 DSH 配置。', loadingSettings: '正在读取设置…',
      requestSent: '已发送 NapCat 操作请求。', stoppedNotice: 'NapCat 已停止。', profile: 'DSH 配置', ready: 'QQ 已连接', noConnection: 'QQ 尚未连接', statusUnavailable: '无法读取连接状态。',
    }
    const icons = {
      spark: 'M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3zM19 14l1.1 3.1L23 18l-2.9 1-1.1 3-1-3-3-1 3-1 1-3z',
      chat: 'M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l-3 2 1-4.5A7.5 7.5 0 1 1 20 11.5zM7 10h8M7 14h5',
      folder: 'M3 7.5A1.5 1.5 0 0 1 4.5 6H10l2 2h7.5A1.5 1.5 0 0 1 21 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z',
      person: 'M20 21a8 8 0 0 0-16 0M12 13a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
      play: 'M8 5v14l11-7z', stop: 'M6 6h12v12H6z', refresh: 'M20 7v5h-5M4 17v-5h5m10-3a7 7 0 0 0-12-2L4 12m16 0-3 5a7 7 0 0 1-12 0',
      check: 'M20 6 9 17l-5-5', info: 'M12 16v-4m0-4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0z',
    }
    function Icon({ name, size = 17 }) {
      return h('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }, h('path', { d: icons[name] || icons.spark }))
    }
    function installStyles() {
      if (typeof document === 'undefined' || document.getElementById(stylesId)) return
      const style = document.createElement('style')
      style.id = stylesId
      style.textContent = css
      document.head.appendChild(style)
    }
    function createSettingsPage(t) {
      return function LuoyuSettings() {
        const [settings, setSettings] = React.useState(null)
        const [saved, setSaved] = React.useState(null)
        const [status, setStatus] = React.useState(null)
        const [busy, setBusy] = React.useState(false)
        const [notice, setNotice] = React.useState('')
        const [error, setError] = React.useState('')
        const [qrStamp, setQrStamp] = React.useState(0)

        const loadSettings = React.useCallback(async () => {
          try {
            const response = await fetch(`${endpoint}/settings`, { cache: 'no-store' })
            if (!response.ok) throw new Error('Unavailable')
            const value = await response.json()
            setSettings(value)
            setSaved(value)
            setError('')
          } catch (cause) {
            setError(cause instanceof Error ? cause.message : String(cause))
          }
        }, [])
        const refreshStatus = React.useCallback(async () => {
          try {
            const response = await fetch(`${endpoint}/state`, { cache: 'no-store' })
            if (!response.ok) throw new Error('Unavailable')
            setStatus(await response.json())
          } catch {
            setStatus(null)
          }
        }, [])
        React.useEffect(() => {
          installStyles()
          void loadSettings()
          void refreshStatus()
          const timer = setInterval(() => void refreshStatus(), 5000)
          return () => clearInterval(timer)
        }, [loadSettings, refreshStatus])

        async function act(action) {
          setBusy(true)
          setNotice('')
          setError('')
          try {
            const response = await fetch(`${endpoint}/${action}`, { method: 'POST' })
            const value = await response.json()
            if (!response.ok) throw new Error(value.error || `Request failed (${response.status}).`)
            setQrStamp(Date.now())
            setNotice(action === 'stop' ? t('stoppedNotice') : t('requestSent'))
            await refreshStatus()
          } catch (cause) {
            setError(cause instanceof Error ? cause.message : String(cause))
          } finally {
            setBusy(false)
          }
        }
        async function save(event) {
          event.preventDefault()
          setBusy(true)
          setNotice('')
          setError('')
          try {
            const response = await fetch(`${endpoint}/settings`, {
              method: 'POST', headers: { 'content-type': 'application/json' },
              body: JSON.stringify({
                workspaceDir: settings.workspaceDir, persona: settings.persona,
                privateReply: settings.privateReply, groupReply: settings.groupReply,
              }),
            })
            const value = await response.json()
            if (!response.ok) throw new Error(value.error || `Save failed (${response.status}).`)
            setNotice(value.workspaceChanged ? t('workspaceChanged') : t('saved'))
            await loadSettings()
          } catch (cause) {
            setError(cause instanceof Error ? cause.message : String(cause))
          } finally {
            setBusy(false)
          }
        }

        const phase = status?.sidecar?.phase || 'loading'
        const connected = Boolean(status?.bridge?.connected)
        const account = status?.sidecar?.uin || status?.bridge?.uin || t('unknown')
        const dirty = settings && saved && JSON.stringify(settings) !== JSON.stringify(saved)
        const statusText = connected ? t('online') : phase === 'stopped' ? t('stopped') : phase === 'starting' ? t('starting') : phase === 'unavailable' ? t('unavailable') : t('needsLogin')
        const badgeClass = connected ? 'luoyu__badge--online' : status?.sidecar?.running ? 'luoyu__badge--pending' : ''
        const field = (label, help, control) => h('label', { className: 'luoyu__field' },
          h('span', { className: 'luoyu__field-head' }, h('span', { className: 'luoyu__label' }, label), help ? h('span', { className: 'luoyu__help' }, help) : null), control)
        const panelHead = (name, title, hint) => h('div', { className: 'luoyu__panel-head' },
          h('div', { className: 'luoyu__heading' }, h('span', { className: 'luoyu__icon' }, h(Icon, { name })), h('div', null,
            h('h2', { className: 'luoyu__panel-title' }, title), h('p', { className: 'luoyu__panel-hint' }, hint))))

        return h('main', { className: 'luoyu' },
          h('header', { className: 'luoyu__hero' },
            h('div', { className: 'luoyu__hero-copy' },
              h('span', { className: 'luoyu__mark' }, h(Icon, { name: 'spark', size: 25 })),
              h('div', null, h('p', { className: 'luoyu__eyebrow' }, t('eyebrow')), h('h1', { className: 'luoyu__title' }, t('title')), h('p', { className: 'luoyu__lead' }, t('description')))),
            h('span', { className: 'luoyu__profile' }, h(Icon, { name: 'check', size: 14 }), t('profile'))),
          error ? h('div', { className: 'luoyu__error', role: 'alert' }, error) : null,
          notice ? h('div', { className: 'luoyu__notice', role: 'status' }, notice) : null,
          h('div', { className: 'luoyu__grid' },
            h('section', { className: 'luoyu__panel' },
              panelHead('chat', t('connection'), t('connectionHint')),
              h('div', { className: `luoyu__badge ${badgeClass}` }, h('i', { className: 'luoyu__dot' }), statusText),
              h('div', { className: 'luoyu__facts', style: { marginTop: 14 } },
                h('div', { className: 'luoyu__fact' }, h('span', { className: 'luoyu__fact-label' }, t('account')), h('span', { className: 'luoyu__fact-value' }, account)),
                h('div', { className: 'luoyu__fact' }, h('span', { className: 'luoyu__fact-label' }, t('transport')), h('span', { className: 'luoyu__fact-value' }, connected ? t('connected') : t('disconnected')))),
              h('div', { className: 'luoyu__actions' },
                h('button', { className: 'luoyu__button luoyu__button--primary', type: 'button', disabled: busy || status?.sidecar?.running, onClick: () => void act('start') }, h(Icon, { name: 'play', size: 15 }), t('start')),
                h('button', { className: 'luoyu__button luoyu__button--danger', type: 'button', disabled: busy || !status?.sidecar?.running, onClick: () => void act('stop') }, h(Icon, { name: 'stop', size: 15 }), t('stop')),
                h('button', { className: 'luoyu__button', type: 'button', disabled: busy, onClick: () => void act('refresh-qrcode') }, h(Icon, { name: 'refresh', size: 15 }), t('refreshQr')))),
            h('section', { className: 'luoyu__panel' },
              panelHead('spark', t('qrTitle'), t('qrHint')),
              h('div', { className: 'luoyu__qr' },
                status?.sidecar?.qrcodePath && !connected
                  ? h('img', { src: `${endpoint}/qrcode?t=${qrStamp || status.sidecar.updatedAt}`, alt: t('qrTitle') })
                  : h('span', { className: 'luoyu__qr-placeholder' }, h(Icon, { name: 'chat', size: 32 })),
                h('p', { className: 'luoyu__qr-title' }, status?.sidecar?.qrcodePath && !connected ? t('qrTitle') : t('noConnection')),
                h('p', { className: 'luoyu__qr-copy' }, status?.sidecar?.qrcodePath && !connected ? t('qrHint') : t('qrWaiting')))),
            settings ? h('form', { className: 'luoyu__panel luoyu__panel--wide', onSubmit: save },
              panelHead('folder', t('workspace'), t('workspaceHint')),
              field(t('workspacePath'), t('workspaceHelp'), h('input', { className: 'luoyu__input', value: settings.workspaceDir, onChange: event => setSettings({ ...settings, workspaceDir: event.target.value }), required: true })),
              field(t('persona'), t('personaHelp'), h('textarea', { className: 'luoyu__input luoyu__textarea', value: settings.persona, onChange: event => setSettings({ ...settings, persona: event.target.value }), required: true, maxLength: 50000 })),
              h('label', { className: 'luoyu__toggle-row' }, h('span', { className: 'luoyu__toggle-copy' }, h('span', { className: 'luoyu__label' }, t('privateReply')), h('span', { className: 'luoyu__help' }, t('privateReplyHelp'))), h('input', { className: 'luoyu__check', type: 'checkbox', checked: settings.privateReply, onChange: event => setSettings({ ...settings, privateReply: event.target.checked }) })),
              field(t('groupReply'), t('groupReplyHelp'), h('select', { className: 'luoyu__input', value: settings.groupReply, onChange: event => setSettings({ ...settings, groupReply: event.target.value }) }, h('option', { value: 'balanced' }, t('balanced')), h('option', { value: 'mention' }, t('mention')))),
              h('div', { className: 'luoyu__save-row' }, h('span', { className: 'luoyu__save-note' }, t('saveHint')), h('button', { className: 'luoyu__button luoyu__button--primary', type: 'submit', disabled: busy || !dirty }, busy ? t('saving') : t('save'))))
              : h('section', { className: 'luoyu__panel luoyu__panel--wide' }, h('p', { className: 'luoyu__panel-hint' }, t('loadingSettings')))),
          h('footer', { className: 'luoyu__footer' }, h(Icon, { name: 'info', size: 14 }), t('saveHint')))
      }
    }

    return {
      inject: ['slots', 'locale'],
      apply(ctx) {
        const t = ctx.locale.bind(NS)
        ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'luoyu: dictionaries')
        ctx.slots.inject('settings.section', () => ctx.slots.register({
          name: 'settings.section', id: 'luoyu', order: 30, label: () => t('nav'),
        }, createSettingsPage(t)))
      },
    }
  },
})
