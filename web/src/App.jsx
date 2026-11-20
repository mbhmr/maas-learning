import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const PRESETS = [
  {
    key: 'trader', label: 'FX trader', flag: 'EN',
    profile: {
      name: 'FX trader', language: 'en', seconds: 180, depth: 'dense, every figure with its period',
      description: 'A currency trader. Wants central banks, inflation and macro data, FX moves and the biggest ' +
        'market-moving company news. Numbers first, no background explanations.',
    },
  },
  {
    key: 'investor', label: 'Privatanleger', flag: 'DE',
    profile: {
      name: 'Privatanleger', language: 'de', seconds: 120, depth: 'simple, explain terms in a few words',
      description: 'A private investor in Germany with little time. Wants the big stories of the day in plain ' +
        'language, what happened and why it matters, few numbers.',
    },
  },
  {
    key: 'world', label: 'World news', flag: 'EN',
    profile: {
      name: 'World news', language: 'en', seconds: 150, depth: 'simple, explain terms in a few words',
      description: 'Someone who just wants to know what happened in the world: politics, world events, big ' +
        'business and tech stories, crime and culture. Not an investor, no market jargon, at most one number per story.',
    },
  },
  {
    key: 'belegger', label: 'Belegger', flag: 'NL',
    profile: {
      name: 'Belegger', language: 'nl', seconds: 150, depth: 'medium',
      description: 'A Dutch retail investor who holds tech stocks and some crypto. Wants stocks, AI companies, ' +
        'crypto and the big macro numbers that move them, with the key figure per story and why it matters.',
    },
  },
]
const LANGS = { en: 'English', de: 'Deutsch', nl: 'Nederlands' }
const DEPTHS = ['dense, every figure with its period', 'medium', 'simple, explain terms in a few words']
const STEPS = ['Picking the stories for this listener', 'Writing the script from verified facts',
  'Checking every number and claim against the quotes', 'Recording the voice']

const fmt = (s) => (s == null || isNaN(s) ? '0:00' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`)
// "1 outlet", "3 outlets": numbers with the right plural everywhere in the UI
const pl = (n, one, many = one + 's') => `${Number(n).toLocaleString('en-US')} ${Number(n) === 1 ? one : many}`
const day = (d) => (d ? new Date(String(d).slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '')

// cut for length, an orphaned context line or a greeting without the name: not a truth problem, not counted as blocked
const notChecker = (why) => /^(over the requested|too long for the ear|context for a story whose news|greeting does not call)/.test(String(why))
const isRetry = (why) => /^rewrite blocked/.test(String(why))

async function api(path, body) {
  const r = await fetch(path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  } : undefined)
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail ?? msg } catch { /* not json */ }
    if (r.status >= 500) msg = `Something went wrong on the server (${msg}). Try again, or pick a listener that is already cached.`
    if (r.status === 429) msg = 'Too many new briefings at once. This demo caps new briefings to protect its credits. ' +
      `Try again in ${r.headers.get('Retry-After') || 'a few'} seconds, or pick a listener that is already cached.`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return r.json()
}

/* Section header: small label, a thin rule to the right edge, an optional count. */
function Head({ children, count, as = 'h2', className = '' }) {
  const Tag = as
  return (
    <Tag className={`sect ${className}`}>
      <span>{children}</span><i aria-hidden />{count != null && count !== '' && <small>{count}</small>}
    </Tag>
  )
}

const THEME_ICON = {
  dark: <path d="M14.5 3.5a7 7 0 1 0 6 10.5 6 6 0 0 1-6-10.5z" />,
  light: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" /></>,
  '': <><circle cx="12" cy="12" r="8" /><path d="M12 4a8 8 0 0 1 0 16z" className="fill" /></>,
}

/* The quote with the stated value highlighted, so the eye finds the number at once. */
function Quote({ quote, value }) {
  const v = (value || '').trim()
  const i = v ? quote.toLowerCase().indexOf(v.toLowerCase()) : -1
  if (i < 0) return <>{quote}</>
  return <>{quote.slice(0, i)}<mark>{quote.slice(i, i + v.length)}</mark>{quote.slice(i + v.length)}</>
}

function SourceCard({ s, lang }) {
  const [state, setState] = useState('idle')
  const audio = useRef(null)
  const listen = async () => {
    if (audio.current) { audio.current.currentTime = 0; audio.current.play(); return }
    setState('loading')
    try {
      const r = await fetch('/api/quote-audio', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ quote: s.quote, lang: s.language || 'en' }),
      })
      if (!r.ok) throw new Error()
      audio.current = new Audio(URL.createObjectURL(await r.blob()))
      audio.current.onended = () => setState('idle')
      setState('playing')
      audio.current.play()
    } catch { setState('none') }
  }
  return (
    <article className={`card ${s.conflict ? 'conflict' : ''}`}>
      <header>
        <span className="outlet">{s.publisher}</span>
        <span className="date">{day(s.date)}</span>
      </header>
      {s.conflict && <p className="warn">Sources disagree on this figure.</p>}
      <blockquote><Quote quote={s.quote} value={s.value} /></blockquote>
      <footer>
        <a className="srclink" href={s.evidenceUrl} target="_blank" rel="noreferrer" title="Opens the article with this quote highlighted">Open source ↗</a>
        {state !== 'none' && (
          <button className="ghost small" onClick={listen} disabled={state === 'loading'} title="Hear the quote read aloud">
            {state === 'loading' ? 'Loading…' : 'Hear quote'}
          </button>
        )}
      </footer>
      {Object.keys(s.translations || {}).length > 0 && (
        <p className="translations">Also in {Object.entries(s.translations).map(([l, t], n) => (
          <span key={l}>{n ? ', ' : ''}<a href={t.url} target="_blank" rel="noreferrer">{String(l).toUpperCase()}</a></span>))}
        </p>
      )}
    </article>
  )
}

function Evidence({ claim, mode, progress, onFollow, lang, onClose }) {
  if (!claim) return (
    <div className="evidence empty">
      <Head>Evidence</Head>
      <p className="hint">Press play. Each sentence's source appears here.</p>
    </div>
  )
  return (
    <div className={`evidence ${mode}`}>
      <div className="evidence-top">
        <Head>
          {mode === 'live' && <b className="livedot" aria-hidden />}
          {mode === 'pinned' ? 'Selected' : mode === 'preview' ? 'Evidence' : 'Now speaking'}
        </Head>
        <div className="evidence-actions">
          {mode === 'pinned' && <button className="ghost small" onClick={onFollow}>Follow audio</button>}
          <button className="ghost small close" onClick={onClose} aria-label="Close">✕</button>
        </div>
      </div>
      <div className="spoken">
        <p>{claim.text}</p>
        {progress != null && <span className="sprog" aria-hidden><i style={{ width: `${progress * 100}%` }} /></span>}
      </div>
      {mode === 'preview' && <p className="hint">Press play and this follows the voice.</p>}
      {claim.sources.length === 0
        ? <p className="muted">{claim.kind === 'disclosure'
          ? 'Fixed disclosure line.'
          : claim.kind === 'host' ? 'Greeting. No facts or figures allowed.'
          : 'No figure in this line.'}</p>
        : <>
          {claim.kind === 'context' && <p className="reading" title="Interprets the quotes below. The checker blocks any figure not in them.">
            Our reading of these quotes. No new figures.</p>}
          <p className="backing">{pl(claim.sources.length, 'verified quote')} · {pl(new Set(claim.sources.map(s => s.publisher)).size, 'outlet')}</p>
          {claim.sources.map((s) => <SourceCard key={s.articleId + s.quote} s={s} lang={lang} />)}
        </>}
    </div>
  )
}

function Newsroom({ dayId }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(null)
  const [only, setOnly] = useState(false)
  useEffect(() => {
    if (!dayId) return
    setData(null); setErr('')
    fetch(`/api/stories/${dayId}`).then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(setData).catch(e => setErr(e.message))
  }, [dayId])
  if (err) return <div className="error">Could not load the story list: {err}</div>
  if (!data) return <div className="muted">Loading stories…</div>
  const list = only ? data.stories.filter(s => s.selected) : data.stories
  const articles = data.stories.reduce((n, s) => n + s.articleCount, 0)
  return (
    <section className="newsroom">
      <div className="nr-head">
        <h2>{pl(articles, 'article')} → {pl(data.stories.length, 'story', 'stories')}</h2>
        <p className="muted">One event across outlets and languages is one story. The top stories get their facts checked once a day.</p>
      </div>
      <Head as="div" count={only ? `${list.length} checked` : day(data.day)}>
        <label className="toggle"><input type="checkbox" checked={only} onChange={e => setOnly(e.target.checked)} /> Only checked stories</label>
      </Head>
      <ol className="nr-list">
        {list.map(s => (
          <li key={s.id} className={`nr-story ${open === s.id ? 'open' : ''}`}>
            <button className="nr-row" onClick={() => setOpen(open === s.id ? null : s.id)} aria-expanded={open === s.id}>
              <span className="nr-rank">{s.rank}</span>
              <span className="nr-title">{s.title}<small>{s.topic}</small></span>
              <span className="nr-meta">
                <span><b>{s.articleCount}</b> {s.articleCount === 1 ? 'article' : 'articles'}{s.articles.length > s.articleCount ? ` + ${s.articles.length - s.articleCount} translated` : ''}</span>
                <span><b>{s.outlets.length}</b> {s.outlets.length === 1 ? 'outlet' : 'outlets'}</span>
                <span>{(s.languages || []).map(l => String(l).toUpperCase()).join(' · ')}</span>
                {s.hasFacts ? <span className="nr-facts"><b>{s.factCount}</b> {s.factCount === 1 ? 'fact' : 'facts'}</span> : <span className="muted">no facts</span>}
              </span>
            </button>
            {open === s.id && (
              <ul className="nr-articles">
                {s.articles.map(a => (
                  <li key={a.id}>
                    <span className="nr-pub">{a.publisher}</span>
                    <a href={a.url} target="_blank" rel="noreferrer">{a.headline}</a>
                    <small>{a.language ? `${a.language.toUpperCase()}` : ''}{a.translationOf ? ' · translation' : ''} · {day(a.date)}</small>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}

/* The trust receipt: one quiet row of numbers, only from what the API returns. Hover or tap explains each. */
function Receipt({ briefing, claims, stats, blockedOpen, onBlocked }) {
  const [tip, setTip] = useState(null)
  const n = (x) => Number(x).toLocaleString('en-US')
  const w = (x, one, many = one + 's') => (Number(x) === 1 ? one : many)
  const p = briefing.pipeline
  const has = (k) => p && p[k] != null
  const spoken = claims.filter(c => c.kind === 'claim' || c.kind === 'context').length
  const bare = claims.filter(c => /\d/.test(c.text) && c.sources.length === 0).length
  const ac = briefing.audioCheck
  const misses = ac?.mismatches?.length || 0

  const flow = p ? [
    has('articlesRead') && { k: 'read', v: p.articlesRead, l: w(p.articlesRead, 'article'),
      t: `Newstex articles of the news window, grouped after buy/sell pitches and round-ups were dropped${has('outlets') ? `, from ${n(p.outlets)} outlets` : ''}.` },
    has('stories') && { k: 'stories', v: p.stories, l: w(p.stories, 'story', 'stories'),
      t: 'Articles about the same event, across outlets and languages, are grouped into one story and ranked.' },
    has('factsChecked') && { k: 'facts', v: p.factsChecked, l: 'facts checked',
      t: `From the top ${has('storiesWithFacts') ? n(p.storiesWithFacts) + ' ' : ''}stories, every fact is pulled out with the verbatim quote it rests on, and value, unit, date and entity are matched against that quote${has('sourcesRejected') ? `: ${n(p.sourcesRejected)} facts rejected` : ''}.` },
  ].filter(Boolean) : [
    { k: 'quotes', v: stats.quotes, l: `verified ${w(stats.quotes, 'quote')}`, t: 'The verbatim quotes behind this briefing, each checked against its article.' },
    { k: 'outlets', v: stats.outlets, l: w(stats.outlets, 'outlet'), t: 'The different publishers those quotes come from.' },
  ]
  flow.push({ k: 'spoken', v: spoken, l: 'sentences spoken',
    t: 'Only sentences built from verified facts reach the voice, and each one links to its quotes.' })

  const checks = [
    { k: 'blocked', v: stats.blocked, l: 'blocked', click: onBlocked, on: blockedOpen,
      t: 'Lines the model wrote but the checker could not back with a quote. Never spoken. Tap to read them.' },
    { k: 'bare', v: bare, l: 'figures without source', bad: bare > 0,
      t: 'Any spoken sentence with a number must cite a quote that contains that number.' },
    stats.conflicts > 0 && { k: 'conflict', v: stats.conflicts, l: w(stats.conflicts, 'conflict'),
      t: 'Where outlets report different figures, the briefing says so instead of picking one.' },
    ac && ac.checked > 0 && { k: 'ear', v: `${ac.ok}/${ac.checked}`, l: 'heard back', bad: ac.ok !== ac.checked,
      t: `Speech recognition listened to the finished audio: every figure was heard in ${ac.ok} of ${ac.checked} spoken lines with figures${misses ? `, ${misses} flagged` : ''}.` },
  ].filter(Boolean)

  const active = [...flow, ...checks].find(s => s.k === tip)
  const item = (s, first) => (
    <li key={s.k} className={first ? 'split' : ''}>
      <button className={`fig ${s.bad ? 'bad' : ''} ${s.on ? 'on' : ''} ${tip === s.k ? 'tip' : ''} ${s.click ? 'link' : ''}`}
        onMouseEnter={() => setTip(s.k)} onFocus={() => setTip(s.k)}
        onClick={() => { setTip(s.k); s.click?.() }} aria-describedby={tip === s.k ? 'receipt-tip' : undefined}>
        <b>{typeof s.v === 'number' ? n(s.v) : s.v}</b><span>{s.l}</span>
      </button>
    </li>
  )
  return (
    <section className="receipt" aria-label="How this briefing was made" onMouseLeave={() => setTip(null)}>
      <ul className="figs">
        {flow.map(s => item(s, false))}
        {checks.map((s, i) => item(s, i === 0))}
      </ul>
      {active && <p id="receipt-tip" className="receipt-tip" role="status">{active.t}</p>}
    </section>
  )
}

function Timeline({ claims, duration, time, onSeek }) {
  if (!duration) return <div className="timeline idle" />
  return (
    <div className="timeline" onClick={(e) => {
      const r = e.currentTarget.getBoundingClientRect()
      onSeek(((e.clientX - r.left) / r.width) * duration)
    }}>
      {claims.filter(c => c.start != null).map((c) => (
        <span key={c.id} className={`seg ${c.kind} ${c.kind === 'claim' && c.sources.some(s => s.conflict) ? 'conflict' : ''} ${time >= c.start ? 'done' : ''}`}
          style={{ left: `${(c.start / duration) * 100}%`, width: `${Math.max(0.4, ((c.end - c.start) / duration) * 100)}%` }}
          title={c.text} />
      ))}
      <span className="head" style={{ left: `${(time / duration) * 100}%` }} />
    </div>
  )
}

export default function App() {
  const [days, setDays] = useState([])
  const [dayId, setDayId] = useState('')
  const [preset, setPreset] = useState('trader')
  const [custom, setCustom] = useState({ name: '', language: 'en', seconds: 90, depth: 'medium', description: '', mode: 'personal' })
  const [briefing, setBriefing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [rate, setRate] = useState(1)
  const [pinned, setPinned] = useState(null)
  const [sheet, setSheet] = useState(false)
  const [tab, setTab] = useState('said')
  const [view, setView] = useState('briefing')
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('theme') || '' } catch { return '' }
  })
  const audio = useRef(null)
  const lineRefs = useRef({})

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('theme', theme) } catch { /* private mode */ }
  }, [theme])

  useEffect(() => {
    api('/api/days').then((d) => { setDays(d); setDayId(d[0] || '') })
      .catch(() => setError('The API is not running. Start it with: .venv/Scripts/uvicorn api:app --port 8000'))
  }, [])

  const profile = preset === 'custom' ? custom : PRESETS.find(p => p.key === preset).profile

  const generate = async (p = profile) => {
    if (!dayId) return
    setBusy(true); setError(''); setStep(0); setPinned(null); setTab('said')
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 6000)
    try {
      const { mode = 'personal', ...prof } = p
      const b = await api('/api/briefing', { day: dayId, profile: { ...prof, name: prof.name || 'Listener' }, mode })
      setBriefing(b); setTime(0); setPlaying(false)
    } catch (e) {
      setError(e.message)
    } finally {
      clearInterval(timer); setBusy(false)
    }
  }

  // first visit: show the cached trader briefing right away (no new cost)
  useEffect(() => { if (dayId && !briefing) generate(PRESETS[0].profile) }, [dayId]) // eslint-disable-line

  const claims = briefing?.claims || []
  const current = useMemo(() => {
    const spoken = claims.filter(c => c.start != null && c.start <= time + 0.05)
    return spoken.length ? spoken[spoken.length - 1] : null
  }, [claims, time])
  // before play, the evidence panel previews the first checked sentence instead of sitting empty
  const preview = !pinned && !current ? claims.find(c => c.kind === 'claim' && c.sources.length) : null
  const shown = pinned ? claims.find(c => c.id === pinned) : current || preview
  const evMode = pinned ? 'pinned' : current ? 'live' : 'preview'
  const progress = evMode === 'live' && current.end > current.start
    ? Math.min(1, Math.max(0, (time - current.start) / (current.end - current.start))) : null

  // optional chime at the end of each checked fact; fires only on normal playback, never on a seek
  const [chime, setChime] = useState(false)
  const sounds = useRef(null)
  const lastT = useRef(0)
  const ring = (name) => {
    const a = sounds.current?.[name]
    if (a) { a.currentTime = 0; a.play().catch(() => {}) }
  }
  const toggleChime = () => {
    if (!sounds.current) {
      sounds.current = { verified: new Audio('/api/sound/verified.mp3'), conflict: new Audio('/api/sound/conflict.mp3') }
      Object.values(sounds.current).forEach(a => { a.volume = 0.6; a.preload = 'auto' })
    }
    if (!chime) ring('verified')
    setChime(!chime)
  }
  const onTime = (e) => {
    const t = e.target.currentTime, prev = lastT.current
    lastT.current = t
    setTime(t)
    if (!chime || e.target.paused || e.target.seeking || t <= prev || t - prev > 1.5) return
    const hit = claims.filter(c => c.kind === 'claim' && c.end != null && c.end > prev && c.end <= t)
    if (hit.length) ring(hit[hit.length - 1].sources.some(s => s.conflict) ? 'conflict' : 'verified')
  }
  // only factual claims carry a source chip; a context line is interpretation, not proof
  const nowOutlets = current && current.kind === 'claim' ? [...new Set(current.sources.map(s => s.publisher))] : []

  useEffect(() => {
    if (!current || pinned || !playing) return
    lineRefs.current[current.id]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [current?.id]) // eslint-disable-line

  useEffect(() => { if (audio.current) audio.current.playbackRate = rate }, [rate, briefing])

  const seek = (t) => { if (audio.current) { audio.current.currentTime = t; setTime(t) } }
  const jingle = useRef(null)
  const [intro, setIntro] = useState(false)
  // the station jingle (ElevenLabs Music) plays once before the briefing starts from the top
  const toggle = () => {
    if (!audio.current) return
    if (intro) { jingle.current.pause(); setIntro(false); return }
    if (playing) { audio.current.pause(); return }
    if (audio.current.currentTime < 0.2 && jingle.current) {
      jingle.current.currentTime = 0
      jingle.current.play().then(() => setIntro(true)).catch(() => audio.current.play())
    } else audio.current.play()
  }
  const openClaim = (c) => { setPinned(c.id); setSheet(true); if (c.start != null) seek(c.start) }

  const stats = useMemo(() => {
    const src = claims.flatMap(c => c.sources)
    return {
      claims: claims.filter(c => c.kind === 'claim').length,
      quotes: new Set(src.map(s => s.quote)).size,
      outlets: new Set(src.map(s => s.publisher)).size,
      blocked: (briefing?.dropped || []).filter(d => !notChecker(d.why) && !isRetry(d.why)).length,
      conflicts: src.filter(s => s.conflict).length,
    }
  }, [claims, briefing])

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <h1>The Liquid Briefing</h1>
          <p>Personal audio news. Every figure linked to its source.</p>
        </div>
        <nav className="views" aria-label="View">
          <button className={view === 'briefing' ? 'on' : ''} onClick={() => setView('briefing')}>Briefing</button>
          <button className={view === 'newsroom' ? 'on' : ''} onClick={() => setView('newsroom')}>Newsroom</button>
        </nav>
        <button className="ghost icon themebtn" onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? '' : 'dark')}
          title={`Theme: ${theme || 'auto'} (click to switch)`} aria-label={`Theme: ${theme || 'auto'}`}>
          <svg viewBox="0 0 24 24" aria-hidden>{THEME_ICON[theme] || THEME_ICON['']}</svg>
        </button>
      </header>

      {view === 'newsroom' ? <main className="wide"><Newsroom dayId={dayId} /></main> : (
      <main className="grid">
        <aside className="left">
          <section className="panel">
            <Head>Listener</Head>
            <div className="presets">
              {PRESETS.map(p => (
                <button key={p.key} className={`chip ${preset === p.key ? 'on' : ''}`}
                  onClick={() => { setPreset(p.key); generate(p.profile) }} disabled={busy}>
                  {p.label} <span className="flag">{p.flag}</span>
                </button>
              ))}
              <button className={`chip wild ${preset === 'custom' ? 'on' : ''}`} onClick={() => setPreset('custom')} disabled={busy}>
                Wildcard
              </button>
            </div>
            {preset === 'custom' && (
              <form className="custom" onSubmit={(e) => { e.preventDefault(); generate() }}>
                <label>Name
                  <input value={custom.name} maxLength={40} placeholder="e.g. Lena"
                    onChange={(e) => setCustom({ ...custom, name: e.target.value })} />
                </label>
                <label>Who are they?
                  <textarea rows={4} required minLength={10} maxLength={1000} value={custom.description}
                    placeholder="e.g. A student in Maastricht who follows AI companies and crypto, wants it short and fun."
                    onChange={(e) => setCustom({ ...custom, description: e.target.value })} />
                </label>
                <div className="row">
                  <label>Language
                    <select value={custom.language} onChange={(e) => setCustom({ ...custom, language: e.target.value })}>
                      {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </label>
                  <label>Depth
                    <select value={custom.depth} onChange={(e) => setCustom({ ...custom, depth: e.target.value })}>
                      {DEPTHS.map(d => <option key={d} value={d}>{d.split(',')[0]}</option>)}
                    </select>
                  </label>
                </div>
                <label>Length: about {custom.seconds} s
                  <input type="range" min={30} max={180} step={15} value={custom.seconds}
                    onChange={(e) => setCustom({ ...custom, seconds: Number(e.target.value) })} />
                </label>
                <label className="toggle"><input type="checkbox" checked={custom.mode === 'edition'}
                  onChange={(e) => setCustom({ ...custom, mode: e.target.checked ? 'edition' : 'personal' })} />
                  <span title="One recording for everyone with similar interests, only the greeting is personal.">Shared edition, about 18× cheaper at 100,000 listeners</span></label>
                <button className="primary" disabled={busy}>Generate briefing</button>
              </form>
            )}
            {days.length > 1 && (
              <label className="dayselect">News up to
                <select value={dayId} onChange={(e) => setDayId(e.target.value)}>
                  {days.map(d => <option key={d} value={d}>{day(d)} {String(d).slice(0, 4)}</option>)}
                </select>
              </label>
            )}
          </section>

          {briefing && (
            <section className="panel story-panel">
              <Head count={briefing.stories.length}>Stories</Head>
              <ol className="stories">
                {briefing.stories.map(s => (
                  <li key={s.rank}><span>{s.title}</span><small>{pl(s.articles, 'article')}</small></li>
                ))}
              </ol>
            </section>
          )}
        </aside>

        <section className="center">
          {error && <div className="error">{error}</div>}
          {busy && (
            <div className="busy">
              <div className="pulse" />
              <ol>{STEPS.map((s, n) => <li key={s} className={n < step ? 'done' : n === step ? 'now' : ''}>{s}</li>)}</ol>
              <p className="muted">New listener: about 30 to 60 s. Cached: instant.</p>
            </div>
          )}
          {briefing && !busy && (
            <>
              {preset === 'custom' && briefing.profile?.description !== custom.description && (
                <p className="muted">Still playing {briefing.profile?.name}. Describe your listener and create the briefing.</p>
              )}
              <div className="player">
                <button className="play" onClick={toggle} disabled={!briefing.audioUrl} aria-label={playing || intro ? 'Pause' : 'Play'}>
                  {playing || intro ? <svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
                    : <svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z" /></svg>}
                </button>
                <div className="player-main">
                  <div className="player-meta">
                    <div className="who">
                      <strong>{briefing.profile.name}</strong>
                      <span className="lang">{LANGS[briefing.profile.language] || briefing.profile.language}</span>
                      {briefing.mode === 'edition' && briefing.edition && (
                        <span className="edition" title={`Edition ${briefing.edition.key}`}>Shared edition · {briefing.edition.label}{briefing.edition.listeners > 1 ? ` · ${briefing.edition.listeners} listeners` : ''}</span>)}
                    </div>
                    <span className="clock">{intro ? '♪ station jingle' : `${fmt(time)} / ${fmt(duration)}`}</span>
                  </div>
                  <Timeline claims={claims} duration={duration} time={time} onSeek={seek} />
                  <div className="player-tools">
                    {nowOutlets.length > 0 && (
                      <button className="nowsrc" onClick={() => setSheet(true)}>
                        <span>{nowOutlets.join(', ')}</span> <u>quote</u>
                      </button>
                    )}
                    <button className={`switch ${chime ? 'on' : ''}`} aria-pressed={chime} onClick={toggleChime}
                      title="Plays a short chime after each checked fact, a different one where sources disagree">
                      <i aria-hidden /> Chime per checked fact
                    </button>
                    <button className="ghost small rate" onClick={() => setRate(rate === 1 ? 1.25 : rate === 1.25 ? 1.5 : 1)}
                      aria-label="Playback speed">{rate}×</button>
                  </div>
                </div>
                {briefing.audioUrl && (<>
                  <audio ref={jingle} src="/api/sound/jingle.mp3" preload="auto"
                    onEnded={() => { setIntro(false); audio.current?.play() }} onError={() => setIntro(false)} />
                  <audio ref={audio} src={briefing.audioUrl} preload="auto"
                    onTimeUpdate={onTime}
                    onSeeking={(e) => { lastT.current = e.target.currentTime }}
                    onLoadedMetadata={(e) => { setDuration(e.target.duration); lastT.current = e.target.currentTime }}
                    onPlay={(e) => { lastT.current = e.target.currentTime; setPlaying(true) }}
                    onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
                </>)}
              </div>

              <Receipt briefing={briefing} claims={claims} stats={stats} blockedOpen={tab === 'cut'}
                onBlocked={() => setTab(tab === 'cut' ? 'said' : 'cut')} />

              <div className="tabs" role="tablist" aria-label="Transcript">
                <button role="tab" aria-selected={tab === 'said'} className={tab === 'said' ? 'on' : ''} onClick={() => setTab('said')}>
                  Transcript</button>
                <button role="tab" aria-selected={tab === 'cut'} className={tab === 'cut' ? 'on' : ''} onClick={() => setTab('cut')}>
                  Blocked <small>{stats.blocked}</small></button>
              </div>

              {tab === 'said' ? (
                <div className="transcript">
                  {claims.map(c => {
                    const outlets = c.kind === 'claim' ? [...new Map(c.sources.map(s => [s.publisher, s])).values()] : []
                    return (
                      <p key={c.id} ref={(el) => { lineRefs.current[c.id] = el }}
                        className={`line ${c.kind} ${current?.id === c.id ? 'now' : ''} ${pinned === c.id ? 'pin' : ''}
                          ${c.start != null && time > c.end ? 'past' : ''}`}
                        style={current?.id === c.id && progress != null ? { '--p': progress } : undefined}
                        onClick={() => openClaim(c)}>
                        {c.kind === 'context' && <span className="tag">Why it matters</span>}
                        <span className="text">{c.text}</span>
                        {outlets.map(s => (
                          <span key={s.publisher} className={`src ${s.conflict ? 'conflict' : ''}`}>
                            {s.publisher}{c.sources.length > 1 && outlets.length === 1 ? ` ×${c.sources.length}` : ''}{s.conflict && ' · differs'}
                          </span>
                        ))}
                      </p>
                    )
                  })}
                </div>
              ) : (
                <div className="cut">
                  <p className="muted">Written by the model, <b>never spoken</b>. Struck through: no quote backs it. Faded: cut for length or style.</p>
                  {(briefing.dropped || []).map((d, n) => (
                    <div key={n} className={`cutline ${notChecker(d.why) ? 'length' : ''}`}>
                      <s>{d.text}</s>
                      <span>{String(d.why).replace('content check: ', 'content check · ')}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </section>

        <aside className={`right ${sheet ? 'open' : ''}`}>
          <Evidence claim={shown} mode={evMode} progress={progress} lang={briefing?.profile.language}
            onFollow={() => setPinned(null)} onClose={() => { setSheet(false); setPinned(null) }} />
        </aside>
      </main>)}
      {sheet && <div className="scrim" onClick={() => { setSheet(false); setPinned(null) }} />}
    </div>
  )
}
