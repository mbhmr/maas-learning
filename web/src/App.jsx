import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const PRESETS = [
  {
    key: 'trader', label: 'FX trader', flag: 'EN',
    profile: {
      name: 'FX trader', language: 'en', seconds: 120, depth: 'dense, every figure with its period',
      description: 'A currency trader. Wants central banks, inflation and macro data, FX moves and the biggest ' +
        'market-moving company news. Numbers first, no background explanations.',
    },
  },
  {
    key: 'investor', label: 'Privatanleger', flag: 'DE',
    profile: {
      name: 'Privatanleger', language: 'de', seconds: 75, depth: 'simple, explain terms in a few words',
      description: 'A private investor in Germany with little time. Wants the big stories of the day in plain ' +
        'language, what happened and why it matters, few numbers.',
    },
  },
  {
    key: 'world', label: 'World news', flag: 'EN',
    profile: {
      name: 'World news', language: 'en', seconds: 90, depth: 'simple, explain terms in a few words',
      description: 'Someone who just wants to know what happened in the world: politics, world events, big ' +
        'business and tech stories, crime and culture. Not an investor, no market jargon, at most one number per story.',
    },
  },
  {
    key: 'belegger', label: 'Belegger', flag: 'NL',
    profile: {
      name: 'Belegger', language: 'nl', seconds: 90, depth: 'medium',
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
const day = (d) => (d ? new Date(d + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '')

async function api(path, body) {
  const r = await fetch(path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  } : undefined)
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail ?? msg } catch { /* not json */ }
    if (r.status === 429) msg = 'Too many new briefings at once. This demo caps new briefings to protect its credits. ' +
      `Try again in ${r.headers.get('Retry-After') || 'a few'} seconds, or pick a listener that is already cached.`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return r.json()
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
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ quote: s.quote, lang }),
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
      {s.conflict && <p className="warn">Sources disagree on this figure. Both are named in the briefing.</p>}
      <blockquote><Quote quote={s.quote} value={s.value} /></blockquote>
      <footer>
        <a className="open" href={s.evidenceUrl} target="_blank" rel="noreferrer">Open original, quote highlighted ↗</a>
        {state !== 'none' && (
          <button className="ghost" onClick={listen} disabled={state === 'loading'}>
            {state === 'loading' ? 'Loading…' : '▶ Hear the quote'}
          </button>
        )}
      </footer>
      {Object.keys(s.translations || {}).length > 0 && (
        <p className="translations">Also in {Object.entries(s.translations).map(([l, t], n) => (
          <a key={l} href={t.url} target="_blank" rel="noreferrer">{n ? ', ' : ''}{LANGS[l] || l}</a>))}
        </p>
      )}
    </article>
  )
}

function Evidence({ claim, pinned, onFollow, lang, onClose }) {
  if (!claim) return (
    <div className="evidence empty">
      <p className="kicker">Evidence</p>
      <p>Press play. The source of every sentence appears here while you listen.</p>
    </div>
  )
  return (
    <div className="evidence">
      <div className="evidence-top">
        <p className="kicker">{pinned ? 'Pinned evidence' : 'Now speaking'}</p>
        <div className="evidence-actions">
          {pinned && <button className="ghost small" onClick={onFollow}>Follow audio</button>}
          <button className="ghost small close" onClick={onClose} aria-label="Close">✕</button>
        </div>
      </div>
      <p className="spoken">“{claim.text}”</p>
      {claim.sources.length === 0
        ? <p className="muted">{claim.kind === 'disclosure'
          ? 'Fixed line: discloses the synthetic voice and that this is not investment advice.'
          : claim.kind === 'host' ? 'Greeting written for this listener. The checker allows no figures or facts in it.'
          : 'No figure in this line.'}</p>
        : <>
          {claim.kind === 'context' && <p className="reading">Why it matters, our reading. It adds no new facts: it interprets the
            verified quotes below and the checker blocks any figure that is not in them.</p>}
          <p className="muted">{claim.sources.length === 1 ? 'Backed by 1 verified quote' :
            `Backed by ${claim.sources.length} verified quotes from ${new Set(claim.sources.map(s => s.publisher)).size} outlets`}</p>
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
  if (!data) return <div className="panel muted">Loading every story of the day…</div>
  const list = only ? data.stories.filter(s => s.selected) : data.stories
  const articles = data.stories.reduce((n, s) => n + s.articleCount, 0)
  return (
    <section className="newsroom">
      <div className="panel nr-head">
        <div>
          <p className="kicker">Newsroom · {data.day}</p>
          <h2>{articles.toLocaleString()} articles, grouped into {data.stories.length} stories</h2>
          <p className="muted">Same event from several outlets and languages becomes one story. Ranked by importance, outlets and freshness.
            Selected stories get their facts extracted once a day; every listener's briefing is built from those.</p>
        </div>
        <label className="toggle"><input type="checkbox" checked={only} onChange={e => setOnly(e.target.checked)} /> Only stories with checked facts</label>
      </div>
      <ol className="nr-list">
        {list.map(s => (
          <li key={s.id} className={`panel nr-story ${open === s.id ? 'open' : ''}`}>
            <button className="nr-row" onClick={() => setOpen(open === s.id ? null : s.id)} aria-expanded={open === s.id}>
              <span className="nr-rank">{s.rank}</span>
              <span className="nr-title">{s.title}<small>{s.topic}</small></span>
              <span className="nr-meta">
                <span><b>{s.articleCount}</b> articles{s.articles.length > s.articleCount ? ` + ${s.articles.length - s.articleCount} translated` : ''}</span>
                <span><b>{s.outlets.length}</b> outlets</span>
                <span>{s.languages.map(l => l.toUpperCase()).join(' · ')}</span>
                {s.hasFacts ? <span className="nr-facts"><b>{s.factCount}</b> facts</span> : <span className="muted">no facts</span>}
              </span>
            </button>
            {open === s.id && (
              <ul className="nr-articles">
                {s.articles.map(a => (
                  <li key={a.id}>
                    <span className="nr-pub">{a.publisher}</span>
                    <a href={a.url} target="_blank" rel="noreferrer">{a.headline}</a>
                    <small>{a.language.toUpperCase()}{a.translationOf ? ' · translation' : ''} · {String(a.date).slice(0, 16).replace('T', ' ')}</small>
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

function Timeline({ claims, duration, time, onSeek }) {
  if (!duration) return <div className="timeline idle" />
  return (
    <div className="timeline" onClick={(e) => {
      const r = e.currentTarget.getBoundingClientRect()
      onSeek(((e.clientX - r.left) / r.width) * duration)
    }}>
      {claims.filter(c => c.start != null).map((c) => (
        <span key={c.id} className={`seg ${c.kind} ${c.sources.some(s => s.conflict) ? 'conflict' : ''} ${time >= c.start ? 'done' : ''}`}
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
  const shown = pinned ? claims.find(c => c.id === pinned) : current

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
      blocked: (briefing?.dropped || []).filter(d => !String(d.why).startsWith('over the requested')).length,
      conflicts: src.filter(s => s.conflict).length,
    }
  }, [claims, briefing])

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden>
            <svg viewBox="0 0 32 32"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#8b7bff" /><stop offset="1" stopColor="#22d3ee" /></linearGradient></defs><circle cx="16" cy="16" r="15" /><path d="M9 19v-6M13 22V10M17 20v-8M21 18v-4" /></svg>
          </span>
          <div>
            <h1>The <em>Liquid</em> Briefing</h1>
            <p>Your news, read aloud. Every sentence traceable to its source.</p>
          </div>
        </div>
        <nav className="views" aria-label="View">
          <button className={view === 'briefing' ? 'on' : ''} onClick={() => setView('briefing')}>Briefing</button>
          <button className={view === 'newsroom' ? 'on' : ''} onClick={() => setView('newsroom')}>Newsroom</button>
        </nav>
        <button className="ghost small" onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? '' : 'dark')}
          title="Theme">{theme === 'dark' ? '☾ Dark' : theme === 'light' ? '☀ Light' : '◐ Auto'}</button>
      </header>

      {view === 'newsroom' ? <main className="wide"><Newsroom dayId={dayId} /></main> : (
      <main className="grid">
        <aside className="left">
          <section className="panel">
            <p className="kicker">Who is listening?</p>
            <div className="presets">
              {PRESETS.map(p => (
                <button key={p.key} className={`chip ${preset === p.key ? 'on' : ''}`}
                  onClick={() => { setPreset(p.key); generate(p.profile) }} disabled={busy}>
                  {p.label} <span className="flag">{p.flag}</span>
                </button>
              ))}
              <button className={`chip wild ${preset === 'custom' ? 'on' : ''}`} onClick={() => setPreset('custom')} disabled={busy}>
                ✦ Wildcard listener
              </button>
            </div>
            {preset === 'custom' && (
              <form className="custom" onSubmit={(e) => { e.preventDefault(); generate() }}>
                <label>Their name
                  <input value={custom.name} maxLength={40} placeholder="e.g. Lena"
                    onChange={(e) => setCustom({ ...custom, name: e.target.value })} />
                </label>
                <label>Describe them
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
                  Shared edition: one recording for everyone with similar interests, only the greeting is personal (about 18× cheaper at scale)</label>
                <button className="primary" disabled={busy}>Make their briefing</button>
              </form>
            )}
            {days.length > 1 && (
              <label className="dayselect">News up to
                <select value={dayId} onChange={(e) => setDayId(e.target.value)}>
                  {days.map(d => <option key={d}>{d}</option>)}
                </select>
              </label>
            )}
          </section>

          {briefing && (
            <section className="panel">
              <p className="kicker">In this briefing</p>
              <ol className="stories">
                {briefing.stories.map(s => (
                  <li key={s.rank}><span>{s.title}</span><small>{s.articles} articles grouped</small></li>
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
              <p className="muted">A new listener takes about 30 to 60 seconds. The same listener again is instant.</p>
            </div>
          )}
          {briefing && !busy && (
            <>
              <div className="player">
                <button className="play" onClick={toggle} disabled={!briefing.audioUrl} aria-label={playing || intro ? 'Pause' : 'Play'}>
                  {playing || intro ? <svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
                    : <svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z" /></svg>}
                </button>
                <div className="player-main">
                  <div className="player-meta">
                    <strong>{briefing.profile.name}</strong>
                    {briefing.mode === 'edition' && briefing.edition && (
                      <span className="edition" title={`Edition ${briefing.edition.key}`}>Shared edition · {briefing.edition.label}{briefing.edition.listeners > 1 ? ` · ${briefing.edition.listeners} listeners` : ''}</span>)}
                    <span>{intro ? "♪ station jingle" : `${LANGS[briefing.profile.language]} · ${fmt(time)} / ${fmt(duration)}`}</span>
                  </div>
                  <Timeline claims={claims} duration={duration} time={time} onSeek={seek} />
                </div>
                <button className="ghost small" onClick={() => setRate(rate === 1 ? 1.25 : rate === 1.25 ? 1.5 : 1)}>{rate}×</button>
                {briefing.audioUrl && (<>
                  <audio ref={jingle} src="/api/sound/jingle.mp3" preload="auto"
                    onEnded={() => { setIntro(false); audio.current?.play() }} onError={() => setIntro(false)} />
                  <audio ref={audio} src={briefing.audioUrl} preload="auto"
                    onTimeUpdate={(e) => setTime(e.target.currentTime)}
                    onLoadedMetadata={(e) => setDuration(e.target.duration)}
                    onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
                </>)}
              </div>

              <div className="stats">
                <span><b>{stats.claims}</b> spoken claims</span>
                <span><b>{stats.quotes}</b> verified quotes</span>
                <span><b>{stats.outlets}</b> outlets</span>
                {stats.conflicts > 0 && <span className="c"><b>{stats.conflicts}</b> disagreements named</span>}
                <button className={`blocked ${tab === 'cut' ? 'on' : ''}`} onClick={() => setTab(tab === 'cut' ? 'said' : 'cut')}>
                  <b>{stats.blocked}</b> lines blocked by the checker
                </button>
              </div>

              {tab === 'said' ? (
                <div className="transcript">
                  {claims.map(c => {
                    const outlets = [...new Map(c.sources.map(s => [s.publisher, s])).values()]
                    return (
                      <p key={c.id} ref={(el) => { lineRefs.current[c.id] = el }}
                        className={`line ${c.kind} ${current?.id === c.id ? 'now' : ''} ${pinned === c.id ? 'pin' : ''}
                          ${c.start != null && time > c.end ? 'past' : ''}`}
                        onClick={() => openClaim(c)}>
                        {c.kind === 'context' && <span className="tag">Why it matters</span>}
                        <span className="text">{c.text}</span>
                        {outlets.map(s => (
                          <span key={s.publisher} className={`src ${s.conflict ? 'conflict' : ''}`}>
                            {s.conflict && '⚠ '}{s.publisher}{c.sources.length > 1 && outlets.length === 1 ? ` ×${c.sources.length}` : ''}
                          </span>
                        ))}
                      </p>
                    )
                  })}
                </div>
              ) : (
                <div className="cut">
                  <p className="muted">These lines were written by the model and <b>never spoken</b>, because the checker could not
                    find them in the cited quotes. This is what keeps the briefing honest.</p>
                  {(briefing.dropped || []).map((d, n) => (
                    <div key={n} className={`cutline ${String(d.why).startsWith('over the requested') ? 'length' : ''}`}>
                      <s>{d.text}</s>
                      <span>{String(d.why).replace('content check: ', 'content check · ')}</span>
                    </div>
                  ))}
                </div>
              )}
              <p className="disclaimer">Synthetic voice (ElevenLabs). Generated from exactly this transcript. Information, not investment advice.
                {briefing.audioCheck && ` Audio check: ${briefing.audioCheck.ok} of ${briefing.audioCheck.checked} spoken figures confirmed by speech recognition.`}</p>
            </>
          )}
        </section>

        <aside className={`right ${sheet ? 'open' : ''}`}>
          <Evidence claim={shown} pinned={!!pinned} lang={briefing?.profile.language}
            onFollow={() => setPinned(null)} onClose={() => { setSheet(false); setPinned(null) }} />
        </aside>
      </main>)}
      {sheet && <div className="scrim" onClick={() => { setSheet(false); setPinned(null) }} />}
    </div>
  )
}
