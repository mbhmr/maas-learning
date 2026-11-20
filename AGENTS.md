# Maas Learning

Sourcera track, MAIN Summit 2026. Build two distinct personal audio news briefings from Newstex, with article links for each spoken factual claim. See `NOTES.md` for the plan and assignment of work.

## Planned layout and run command

- `data/` holds the private event dataset locally. `output/` holds local demo runs. Ignore both before the first commit.
- Python 3. `src/` handles article processing, verification and provider calls. `prepare.py` runs once per news day (load, cluster, rank, extract facts, cached in `output/`). `app.py` is a Streamlit app: enter any listener profile (the jury brings a live wildcard listener), generate script and audio from the cached facts, show player and transcript with a source link per claim.
- Planned start: `streamlit run app.py` after implementation. Record the verified command, Python version and dataset setup in `README.md`.

## Team rules

- Work on separate branches and in your assigned files. Keep commits small. Review and run the merged flow before using it in the demo.
- Sync before pushing. Push only when the team lead instructs you to do so. Discuss merge conflicts before resolving them.
- Store API keys only in local `.env` and keep it ignored. Commit a placeholder-only `.env.example` if needed. Remove credentials, authorization headers and pinned data from workflow exports.
- Keep Newstex articles and local outputs out of Git and public deployments. Do not republish article text. Delete the dataset after the event under the event terms.
- Use event credits only. Ask the team lead before using paid services, opening new accounts or deploying publicly.
- Verify each spoken claim against the source article, including the value, unit, date, entity and context. Generate speech from the checked transcript.
