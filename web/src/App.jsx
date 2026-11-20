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
    key: 'investor', label: 'German investor', flag: 'DE',
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
    key: 'belegger', label: 'Dutch investor', flag: 'NL',
    profile: {
      name: 'Belegger', language: 'nl', seconds: 150, depth: 'medium',
      description: 'A Dutch retail investor who holds tech stocks and some crypto. Wants stocks, AI companies, ' +
        'crypto and the big macro numbers that move them, with the key figure per story and why it matters.',
    },
  },
]
const LANGS = { en: 'English', de: 'Deutsch', nl: 'Nederlands' }
// the few words that sit inside the spoken text follow the listener's language; the rest of the interface is English
const WORDS = {
  en: { today: 'Today’s briefing', aside: 'Why it matters' },
  de: { today: 'Dein Briefing für heute', aside: 'Warum das zählt' },
  nl: { today: 'Je briefing van vandaag', aside: 'Waarom dit telt' },
}
const DEPTHS = ['dense, every figure with its period', 'medium', 'simple, explain terms in a few words']
const STEPS = ['Picking the stories for this listener', 'Writing the script from verified facts',
  'Checking every number and claim against the quotes', 'Recording the voice']

const fmt = (s) => (s == null || isNaN(s) ? '0:00' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`)
const num = (n) => Number(n).toLocaleString('en-US')
const pl = (n, one, many = one + 's') => `${num(n)} ${Number(n) === 1 ? one : many}`
const day = (d) => (d ? new Date(String(d).slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '')
const longDay = (d) => (d ? new Date(String(d).slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : '')

// cut for length, an orphaned context line or a greeting without the name: not a truth problem, not counted as blocked
const notChecker = (why) => /^(over the requested|too long for the ear|context for a story whose news|greeting does not call)/.test(String(why))
const isRetry = (why) => /^rewrite blocked/.test(String(why))
// the checker's reason in plain words: "numbers not in sources: [2016.0, 2026.0] (rewrite tried)" -> "Figures in no quote: 2016, 2026"
const why = (w) => String(w).replace('content check: ', '').replace(/\s*\(rewrite tried\)/, '')
  .replace(/^numbers not in sources: \[(.*)\]/, (_, l) => 'Figures in no quote: ' + l.split(',').map(x => x.trim().replace(/\.0$/, '')).join(', '))
  .replace(/^repeats an earlier line/, 'Repeats an earlier sentence').replace(/^./, (c) => c.toUpperCase())
  .replace(/^(?!Figures in no quote|Repeats)(.{90,})$/, 'The quotes do not support this reading.')

const store = {
  get: (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : v } catch { return d } },
  set: (k, v) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } },
}

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

const THEME_ICON = {
  dark: <path d="M14.5 3.5a7 7 0 1 0 6 10.5 6 6 0 0 1-6-10.5z" />,
  light: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" /></>,
  '': <><circle cx="12" cy="12" r="8" /><path d="M12 4a8 8 0 0 1 0 16z" className="fill" /></>,
}

/* The quote with the stated value marked, so the eye finds the number at once. */
function Quote({ quote, value }) {
  const v = (value || '').trim()
  const i = v ? quote.toLowerCase().indexOf(v.toLowerCase()) : -1
  if (i < 0) return <>{quote}</>
  return <>{quote.slice(0, i)}<mark>{quote.slice(i, i + v.length)}</mark>{quote.slice(i + v.length)}</>
}

function SourceCard({ s }) {
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
  const langs = Object.entries(s.translations || {})
  return (
    <article className={`card ${s.conflict ? 'conflict' : ''}`}>
      <blockquote><Quote quote={s.quote} value={s.value} /></blockquote>
      <p className="cite"><span className="outlet">{s.publisher}</span>, {day(s.date)}</p>
      {s.conflict && <p className="warn">Outlets report different figures here, so the briefing says so.</p>}
      <p className="card-links">
        <a href={s.evidenceUrl} target="_blank" rel="noreferrer" title="Opens the article with this quote highlighted">Read in the article</a>
        {state !== 'none' && (
          <button className="textbtn" onClick={listen} disabled={state === 'loading'}>
            {state === 'loading' ? 'Loading' : 'Listen to the quote'}
          </button>
        )}
      </p>
      {langs.length > 0 && <p className="also">Also reported in {langs.map(([l, t], n) => (
        <span key={l}>{n ? ', ' : ''}<a href={t.url} target="_blank" rel="noreferrer">{({ en: 'English', de: 'German', nl: 'Dutch' })[l] || String(l).toUpperCase()}</a></span>))}</p>}
    </article>
  )
}

function Evidence({ claim, note, mode, onFollow, onClose }) {
  if (!claim) return <div className="evidence empty"><p className="hint">Tap a sentence to see the quotes behind it.</p></div>
  return (
    <div className={`evidence ${mode}`}>
      <div className="evidence-top">
        <span className="label">{note ? `Quotes for sentence ${note}` : 'Quotes'}</span>
        {mode === 'pinned' && <button className="textbtn" onClick={onFollow}>Follow audio</button>}
        <button className="textbtn close" onClick={onClose} aria-label="Close">Close</button>
      </div>
      <p className="spoken">{note && <sup className="note-ref">{note}</sup>}{claim.text}</p>
      {claim.sources.length === 0
        ? <p className="hint">{claim.kind === 'disclosure' ? 'This line is part of every briefing. It states no facts.'
          : claim.kind === 'host' ? 'A greeting. It may not state any fact or figure.' : 'This line states no figure, so it needs no quote.'}</p>
        : <>
          {claim.kind === 'context' && <p className="hint">Our reading of the quotes below. It may not add any figure.</p>}
          {claim.sources.map((s) => <SourceCard key={s.articleId + s.quote} s={s} />)}
        </>}
    </div>
  )
}

/* The line being spoken, with the word being read marked. Other lines are plain text. */
function Spoken({ text, words, time }) {
  if (!words?.length) return <>{text}</>
  let i = -1
  for (let n = 0; n < words.length && words[n][0] <= time; n++) i = n
  if (i < 0) return <>{text}</>
  const [, , a, b] = words[i]
  return <>{text.slice(0, a)}<span className="word">{text.slice(a, b)}</span>{text.slice(b)}</>
}

function Timeline({ claims, duration, time, onSeek }) {
  const seekAt = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    onSeek(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * duration)
  }
  const keys = (e) => {
    if (e.key === 'ArrowRight') onSeek(Math.min(duration, time + 5))
    if (e.key === 'ArrowLeft') onSeek(Math.max(0, time - 5))
  }
  if (!duration) return <div className="timeline idle" />
  return (
    <div className="timeline" onClick={seekAt} onKeyDown={keys} role="slider" tabIndex={0} aria-label="Position"
      aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(time)} aria-valuetext={fmt(time)}>
      {claims.filter(c => c.start != null).map((c) => (
        <span key={c.id} className={`seg ${c.kind} ${time >= c.start ? 'done' : ''}`}
          style={{ left: `${(c.start / duration) * 100}%`, width: `${Math.max(0.4, ((c.end - c.start) / duration) * 100)}%` }} />
      ))}
      <span className="head" style={{ left: `${(time / duration) * 100}%` }} />
    </div>
  )
}

const VOL_ICON = (v) => (
  <svg viewBox="0 0 24 24" aria-hidden>
    <path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" className="fill" />
    {v > 0 && <path d="M15.5 9.2a4 4 0 0 1 0 5.6" />}
    {v > 0.5 && <path d="M18 6.8a7.5 7.5 0 0 1 0 10.4" />}
    {v === 0 && <path d="M16 9.5l5 5M21 9.5l-5 5" />}
  </svg>
)

/* How this was made: every pipeline number, the blocked lines and the extras, folded away by default. */
function Making({ briefing, claims, stats, chime, onChime }) {
  const p = briefing.pipeline
  const ac = briefing.audioCheck
  const spoken = claims.filter(c => c.kind === 'claim' || c.kind === 'context').length
  const bare = claims.filter(c => /\d/.test(c.text) && c.sources.length === 0).length
  const rows = [
    p?.articlesRead != null && [num(p.articlesRead), 'articles read', `Newstex articles of the news window${p.outlets != null ? `, from ${num(p.outlets)} outlets` : ''}, after buy and sell pitches and round-ups were dropped.`],
    p?.stories != null && [num(p.stories), 'stories found', 'Articles about the same event, across outlets and languages, are grouped into one story and ranked.'],
    p?.factsChecked != null && [num(p.factsChecked), 'facts checked', `Every fact is pulled out with the verbatim quote it rests on; value, unit, date and entity must match that quote${p.sourcesRejected != null ? `. ${num(p.sourcesRejected)} were rejected` : ''}.`],
    [num(spoken), 'sentences spoken', 'Only sentences built from checked facts reach the voice, and each one links to its quotes.'],
    [num(stats.blocked), 'sentences blocked', 'Written by the model but never spoken: no quote backed them, or they repeated an earlier sentence. Listed below.'],
    [num(bare), 'figures without a source', 'Any spoken sentence with a number must cite a quote that contains that number.'],
    stats.conflicts > 0 && [num(stats.conflicts), stats.conflicts === 1 ? 'conflict' : 'conflicts', 'Where outlets report different figures, the briefing says so instead of picking one.'],
    ac?.checked > 0 && [`${ac.ok} of ${ac.checked}`, 'sentences with figures heard correctly', `Speech recognition listened to the finished audio and checked every figure in the ${ac.checked} spoken sentences that have one.`],
  ].filter(Boolean)
  const blocked = (briefing.dropped || []).filter(d => !notChecker(d.why))
  return (
    <details className="making">
      <summary>How this briefing was made</summary>
      <label className="toggle"><input type="checkbox" checked={chime} onChange={onChime} /> Play a soft chime after each checked fact</label>
      <dl className="facts">
        {rows.map(([v, l, t]) => <div key={l}><dt><b>{v}</b> {l}</dt><dd>{t}</dd></div>)}
      </dl>
      {briefing.mode === 'edition' && briefing.edition && (
        <p className="note">Shared edition “{briefing.edition.label}”{briefing.edition.listeners > 1 ? `, ${num(briefing.edition.listeners)} listeners` : ''}: one recording for everyone with similar interests, only the greeting is personal.</p>
      )}
      {briefing.stories?.length > 0 && <>
        <h3>The stories in this briefing</h3>
        <ul className="stories">{briefing.stories.map(s => <li key={s.rank}>{s.title} <small>rank {s.rank} of the day</small></li>)}</ul>
      </>}
      {blocked.length > 0 && <>
        <h3>Blocked lines</h3>
        <p className="note">Written by the model, never spoken. Each one says why it was stopped.</p>
        <ul className="cut">{blocked.map((d, n) => (
          <li key={n} className="cutline"><span>{d.text}</span><small>{why(d.why)}</small></li>))}
        </ul>
      </>}
    </details>
  )
}

/* Today's ranking: every story of the day in the order the pipeline ranked it, with the reason in a few words.
   The stories this listener hears are marked. reason (one line from the ranking step) is shown when the API sends it. */
function Newsroom({ dayId, briefing }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(null)
  const [all, setAll] = useState(false)
  useEffect(() => {
    if (!dayId) return
    setData(null); setErr('')
    fetch(`/api/stories/${dayId}`).then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(setData).catch(e => setErr(e.message))
  }, [dayId])
  if (err) return <div className="error">Could not load the ranking: {err}</div>
  if (!data) return <p className="hint">Loading the ranking</p>
  const heard = new Set((briefing?.stories || []).map(s => s.title))
  const articles = data.stories.reduce((n, s) => n + s.articleCount, 0)
  const checked = data.stories.filter(s => s.hasFacts).length
  const TOP = 25
  const list = all ? data.stories : data.stories.slice(0, TOP)
  return (
    <section className="newsroom">
      <h2>Today’s ranking</h2>
      <p className="note">{pl(articles, 'article')} became {pl(data.stories.length, 'story', 'stories')}, ranked by how much they matter.
        {briefing ? <> Stories marked <span className="heard-mark">in your briefing</span> are the ones {briefing.profile.name} hears.</> : ''}</p>
      <details className="how">
        <summary>How the ranking works</summary>
        <p className="note">One event across outlets and languages is one story. An editor model rates how much each story matters, from
          1 to 5. That rating counts most, together with the number of outlets, the number of articles and how fresh the news is;
          central bank and currency news get a lift, speculation is pushed down. {num(checked)} stories had every fact checked
          against its quote: the strongest ones, the best of each topic, all macro news and every story two or more outlets
          report. Each listener then gets the checked stories that fit them.</p>
      </details>
      <ol className="nr-list">
        {list.map(s => (
          <li key={s.id} className={`nr-story ${open === s.id ? 'open' : ''} ${heard.has(s.title) ? 'heard' : ''}`}>
            <button className="nr-row" onClick={() => setOpen(open === s.id ? null : s.id)} aria-expanded={open === s.id}>
              <span className="nr-rank">{s.rank}</span>
              <span className="nr-title">{s.title}
                <small>{s.reason || [s.importance != null && `Importance ${s.importance} of 5`, s.topic,
                  pl(s.outlets.length, 'outlet'), !s.hasFacts && 'no checked facts'].filter(Boolean).join(', ')}</small>
              </span>
              {heard.has(s.title) && <span className="heard-mark">in your briefing</span>}
            </button>
            {open === s.id && (
              <ul className="nr-articles">
                {s.articles.map(a => (
                  <li key={a.id}>
                    <a href={a.url} target="_blank" rel="noreferrer">{a.headline}</a>
                    <small>{a.publisher}, {day(a.date)}{a.translationOf ? ', translation' : ''}</small>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
      {!all && data.stories.length > TOP && (
        <button className="textbtn more" onClick={() => setAll(true)}>Show all {num(data.stories.length)} stories</button>)}
    </section>
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
  const [volume, setVolume] = useState(() => Math.min(1, Math.max(0, Number(store.get('volume', 1)) || 0)))
  const [muted, setMuted] = useState(false)
  const [pinned, setPinned] = useState(null)
  const [sheet, setSheet] = useState(false)
  const [view, setView] = useState('briefing')
  const [theme, setTheme] = useState(() => store.get('theme', ''))
  const audio = useRef(null)
  const jingle = useRef(null)
  const lineRefs = useRef({})

  useEffect(() => { document.documentElement.dataset.theme = theme; store.set('theme', theme) }, [theme])

  useEffect(() => {
    api('/api/days').then((d) => { setDays(d); setDayId(d[0] || '') })
      .catch(() => setError('The API is not running. Start it with: .venv/Scripts/uvicorn api:app --port 8000'))
  }, [])

  const profile = preset === 'custom' ? custom : PRESETS.find(p => p.key === preset).profile

  const generate = async (p = profile) => {
    if (!dayId) return
    setBusy(true); setError(''); setStep(0); setPinned(null)
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
  // the sources column shows the latest sentence with sources up to the voice, or the first one before play,
  // so it never goes blank on a greeting or a fixed line
  const sourced = claims.filter(c => c.sources.length)
  const latest = current ? sourced.filter(c => c.start != null && c.start <= current.start).pop() : null
  const shown = pinned ? claims.find(c => c.id === pinned) : latest || sourced.find(c => c.kind === 'claim') || null
  const evMode = pinned ? 'pinned' : current ? 'live' : 'preview'

  // footnote numbers: one per checked news sentence, in reading order
  const notes = useMemo(() => {
    const m = {}
    let n = 0
    claims.forEach(c => { if (c.kind === 'claim' && c.sources.length) m[c.id] = ++n })
    return m
  }, [claims])

  // the clock follows the audio every frame while playing, so the marked word keeps up with the voice
  useEffect(() => {
    if (!playing) return
    let id
    const tick = () => { if (audio.current) setTime(audio.current.currentTime); id = requestAnimationFrame(tick) }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [playing])

  // optional chime at the end of each checked fact; fires only on normal playback, never on a seek
  const [chime, setChime] = useState(false)
  const sounds = useRef(null)
  const lastT = useRef(0)
  const ring = (name) => {
    const a = sounds.current?.[name]
    if (a) { a.currentTime = 0; a.volume = 0.6 * (muted ? 0 : volume); a.play().catch(() => {}) }
  }
  const toggleChime = () => {
    if (!sounds.current) {
      sounds.current = { verified: new Audio('/api/sound/verified.mp3'), conflict: new Audio('/api/sound/conflict.mp3') }
      Object.values(sounds.current).forEach(a => { a.preload = 'auto' })
    }
    if (!chime) ring('verified')
    setChime(!chime)
  }
  const onTime = (e) => {
    const t = e.target.currentTime, prev = lastT.current
    lastT.current = t
    if (!playing) setTime(t)
    if (!chime || e.target.paused || e.target.seeking || t <= prev || t - prev > 1.5) return
    const hit = claims.filter(c => c.kind === 'claim' && c.end != null && c.end > prev && c.end <= t)
    if (hit.length) ring(hit[hit.length - 1].sources.some(s => s.conflict) ? 'conflict' : 'verified')
  }

  useEffect(() => {
    if (!current || pinned || !playing) return
    lineRefs.current[current.id]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [current?.id]) // eslint-disable-line

  useEffect(() => { if (audio.current) audio.current.playbackRate = rate }, [rate, briefing])
  useEffect(() => {
    const v = muted ? 0 : volume
    if (audio.current) audio.current.volume = v
    if (jingle.current) jingle.current.volume = v
    store.set('volume', String(volume))
  }, [volume, muted, briefing])

  const seek = (t) => { if (audio.current) { audio.current.currentTime = t; setTime(t) } }
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
      blocked: (briefing?.dropped || []).filter(d => !notChecker(d.why) && !isRetry(d.why)).length,
      conflicts: src.filter(s => s.conflict).length,
    }
  }, [claims, briefing])

  const vol = muted ? 0 : volume
  // one line of proof above the transcript, from the same numbers as "How this briefing was made"
  const bare = claims.filter(c => /\d/.test(c.text) && c.sources.length === 0).length

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <h1>The Liquid Briefing</h1>
          <p className="tagline">A personal audio news briefing for each listener. Every figure checked against its source.</p>
          {days.length > 1
            ? <label className="daypick"><span className="sr">News of</span>
              <select value={dayId} onChange={(e) => setDayId(e.target.value)}>
                {days.map(d => <option key={d} value={d}>{longDay(d)}</option>)}
              </select></label>
            : <p>{dayId ? longDay(dayId) : ''}</p>}
        </div>
        <nav className="views" aria-label="View">
          <button className={view === 'briefing' ? 'on' : ''} onClick={() => setView('briefing')}>Briefing</button>
          <button className={view === 'newsroom' ? 'on' : ''} onClick={() => setView('newsroom')}>Today’s ranking</button>
          <button className="themebtn" onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? '' : 'dark')}
            title={`Theme: ${theme || 'auto'} (click to switch)`} aria-label={`Theme: ${theme || 'auto'}`}>
            <svg viewBox="0 0 24 24" aria-hidden>{THEME_ICON[theme] || THEME_ICON['']}</svg>
          </button>
        </nav>
      </header>

      {view === 'newsroom' ? <main className="wide"><Newsroom dayId={dayId} briefing={briefing} /></main> : (<>
      <nav className="listeners" aria-label="Listener">
        <span className="label">Listener</span>
        {PRESETS.map(p => (
          <button key={p.key} className={preset === p.key ? 'on' : ''} aria-pressed={preset === p.key}
            onClick={() => { setPreset(p.key); generate(p.profile) }} disabled={busy}>
            {p.label}
          </button>
        ))}
        <button className={preset === 'custom' ? 'on' : ''} aria-pressed={preset === 'custom'} onClick={() => setPreset('custom')} disabled={busy}>
          + Your own listener
        </button>
      </nav>

      <main className="grid">
        <section className="center">
          {preset === 'custom' && (
            <form className="custom" onSubmit={(e) => { e.preventDefault(); generate() }}>
              <label>Who is listening?
                <textarea rows={3} required minLength={10} maxLength={1000} value={custom.description}
                  placeholder="A student in Maastricht who follows AI companies and crypto, wants it short."
                  onChange={(e) => setCustom({ ...custom, description: e.target.value })} />
              </label>
              <div className="row">
                <label>Name
                  <input value={custom.name} maxLength={40} placeholder="Lena"
                    onChange={(e) => setCustom({ ...custom, name: e.target.value })} />
                </label>
                <label>Language
                  <select value={custom.language} onChange={(e) => setCustom({ ...custom, language: e.target.value })}>
                    {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <label>Style
                  <select value={custom.depth} onChange={(e) => setCustom({ ...custom, depth: e.target.value })}>
                    {DEPTHS.map(d => <option key={d} value={d}>{d.split(',')[0]}</option>)}
                  </select>
                </label>
                <label>About {custom.seconds} seconds
                  <input type="range" min={30} max={180} step={15} value={custom.seconds}
                    onChange={(e) => setCustom({ ...custom, seconds: Number(e.target.value) })} />
                </label>
              </div>
              <div className="form-end">
                <label className="toggle"><input type="checkbox" checked={custom.mode === 'edition'}
                  onChange={(e) => setCustom({ ...custom, mode: e.target.checked ? 'edition' : 'personal' })} />
                  <span title="One recording for everyone with similar interests, only the greeting is personal. About 18 times cheaper at 100,000 listeners.">Shared edition</span></label>
                <button className="primary" disabled={busy}>Write this briefing</button>
              </div>
            </form>
          )}
          {error && <div className="error">{error}</div>}
          {busy && (
            <div className="busy" role="status">
              <ol>{STEPS.map((s, n) => <li key={s} className={n < step ? 'done' : n === step ? 'now' : ''}>{s}</li>)}</ol>
              <p className="hint">A new listener takes about half a minute.</p>
            </div>
          )}
          {briefing && !busy && (
            <>
              <div className="player">
                <button className="play" onClick={toggle} disabled={!briefing.audioUrl} aria-label={playing || intro ? 'Pause' : 'Play'}>
                  {playing || intro ? <svg viewBox="0 0 24 24"><rect x="6.5" y="5" width="3.5" height="14" rx="1" /><rect x="14" y="5" width="3.5" height="14" rx="1" /></svg>
                    : <svg viewBox="0 0 24 24"><path d="M8.5 5.5v13l10.5-6.5z" /></svg>}
                </button>
                <div className="player-main">
                  <div className="player-meta">
                    <strong>{preset === 'custom' ? `For ${briefing.profile.name}` : (WORDS[briefing.profile.language] || WORDS.en).today}<span className="lang">, {LANGS[briefing.profile.language] || briefing.profile.language}</span></strong>
                  </div>
                  <Timeline claims={claims} duration={duration} time={time} onSeek={seek} />
                </div>
                <div className="player-tools">
                  <span className="clock">{intro ? 'Station jingle' : `${fmt(time)} / ${fmt(duration)}`}</span>
                  <button className="textbtn rate" onClick={() => setRate(rate === 1 ? 1.25 : rate === 1.25 ? 1.5 : 1)}
                    aria-label={`Playback speed ${rate} times`} title="Playback speed">{rate}×</button>
                  <div className="volume">
                    <button className="iconbtn" onClick={() => setMuted(!muted)} aria-label={muted ? 'Unmute' : 'Mute'} title={muted ? 'Unmute' : 'Mute'}>
                      {VOL_ICON(vol)}
                    </button>
                    <input type="range" min={0} max={1} step={0.05} value={vol} aria-label="Volume"
                      style={{ '--v': `${vol * 100}%` }}
                      onChange={(e) => { setVolume(Number(e.target.value)); setMuted(false) }} />
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

              <p className="hint lead">Select a sentence to read the quotes behind it.{bare ? ` ${pl(bare, 'sentence')} with a figure but no source.` : ''}</p>

              <div className="transcript">
                {claims.map(c => {
                  const now = current?.id === c.id
                  const conflict = c.sources.some(s => s.conflict)
                  return (
                    <p key={c.id} ref={(el) => { lineRefs.current[c.id] = el }}
                      className={`line ${c.kind} ${now ? 'now' : ''} ${shown?.id === c.id ? 'shown' : ''}`}
                      onClick={() => openClaim(c)}>
                      {c.kind === 'context' && <span className="aside">{(WORDS[briefing.profile.language] || WORDS.en).aside}</span>}
                      <span className="text">{now ? <Spoken text={c.text} words={c.words} time={time} /> : c.text}</span>
                      {notes[c.id] && <sup className={`note-ref ${conflict ? 'conflict' : ''}`}
                        title={[...new Set(c.sources.map(s => s.publisher))].join(', ')}>{notes[c.id]}</sup>}
                    </p>
                  )
                })}
              </div>

              <Making briefing={briefing} claims={claims} stats={stats} chime={chime} onChime={toggleChime} />
            </>
          )}
        </section>

        <aside className={`right ${sheet ? 'open' : ''}`}>
          <Evidence claim={shown} note={shown && notes[shown.id]} mode={evMode}
            onFollow={() => setPinned(null)} onClose={() => { setSheet(false); setPinned(null) }} />
        </aside>
      </main>
      </>)}
      {sheet && <div className="scrim" onClick={() => { setSheet(false); setPinned(null) }} />}
    </div>
  )
}
