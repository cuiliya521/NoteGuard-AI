# Forest & Paper × real V2 integration — experiment only

Branch: `experiment/v2-forest-paper-integration`.
Base: V2 `4d3e737004db14c64cc6586480e66f1f9f7552d8`.
This is a working presentation/transaction integration with the real V2 modules, not a static HTML embed. It is **not approved for release**: real online DeepSeek and browser/1440×900 acceptance remain blocked.

## Architecture

- `services/workflow_v2.py`: unchanged rule/semantic orchestration, draft generation and human acceptance/recheck.
- `services/workflow_ai_v2.py`: unchanged DeepSeek JSON review and constrained whole-document suggestions, with the existing explicitly labelled local fallback.
- `services/forest_paper_v2.py`: validates events/documents, stores original/candidate/final independently, applies revision checks, deduplicates submissions and serializes only safe display data.
- `services/forest_paper_ui_v2.py`: Streamlit V1 **custom component**, with bidirectional `setComponentValue` events; server-side calls are real functions. No HTTP audit service, no browser API keys, no public test port.
- `components/forest_paper_v2/`: exact CSS extracted from the final Forest & Paper source, a separate small functional override, HTML and editable JavaScript. No preset audit result or frozen suggestion in runtime code.
- `services/workflow_ui_v2.py`: opt-in hook; the existing V2 remains the default unless `NOTEGUARD_FOREST_PAPER=1`.
- `app.py`: handles the component's navigation request before the existing sidebar widget is constructed. Existing modules remain available from the full V2 app.

Streamlit V1 is deliberately used because this repository already has a V1 clipboard component and the final visual source requires CSS isolation. Its message protocol follows `components/clipboard_paste/index.html`. Official reference: https://docs.streamlit.io/develop/concepts/custom-components/components-v1/intro

## Reproduce locally, without deployment

Check out this experiment branch on an existing authorized computer. Do not switch the formal Streamlit deployment branch.

```sh
python -m venv .venv
# Activate .venv using your operating system's normal command.
python -m pip install streamlit==1.60.0 openai python-dotenv pytest
python -m streamlit run experiments/v2_forest_paper/app.py --global.developmentMode=false --server.address=127.0.0.1 --server.port=8511 --browser.gatherUsageStats=false
```

Open `http://127.0.0.1:8511` in the **same computer's** browser. The independent entry uses the production V2 modules and rules, not demo answers. Other modules are accessed using the full V2 entry, with `NOTEGUARD_FOREST_PAPER=1` and `streamlit run app.py`; install the repository's original requirements for that route. Existing V2 UI remains available by unsetting the flag.

Reuse the existing server-side `DEEPSEEK_API_KEY` configuration. The existing V2 key loader loads `.env` and server environment variables. On Community Cloud, a top-level server Secrets key can populate the environment. Never paste a key into the HTML, JS, an input box, a commit or this report. No new key is requested. Current Work sandbox has no configured key; the formal deployment's credentials were not accessed or copied.

## State semantics

- Audit sends exact title/body to `start_workflow` using the current rules and real semantic/draft callbacks.
- Rule hits and semantic issues are separately labelled. Semantic failure never produces an overall pass. Local fallback is labelled `本地规则`, not LLM success.
- Original and AI candidate remain separate. Accept/edit-accept save an independent final document and call `decide_workflow` to recheck exactly that document.
- Continue-edit buffers are browser-local. Cancel/Esc does not submit a mutation and leaves the confirmed document and its valid review intact.
- Save unchanged final retains its valid review. Save changed final clears review immediately and changes status to `待复检`.
- Recheck failure permits retry; client transport timeout unlocks controls and states that the operation is unconfirmed.
- Every event includes a unique ID and expected workspace version. Duplicates do not repeat provider calls; stale versions are rejected. Old UI render versions/foreign parent messages are ignored.
- Refresh uses an opaque capability token to restore server state. It never trusts browser-supplied detection results. Recovery is process-local, bounded to 128 workspaces and 1 hour of inactivity. Server restart/expiry loses the cache, and explicitly asks for a new audit. It is **not durable authenticated product storage**.

## Automated checks

```sh
python -m pytest tests -q
# DOM event unit tests only; not real browser or API acceptance:
npm install --no-save jsdom
node --test tests/test_forest_paper_component.cjs
```

See `evidence/` and `ACCEPTANCE.md` for actual results. Synthetic semantic callbacks appear only in tests and are not used by the app. No online or screenshot claim is derived from those tests.

## Visual differences from final HTML

1. Runtime data replaces frozen-case answers, so number/length of rule and semantic items varies.
2. Functional original-input dialog, final-document tab, continue-edit and recheck controls are added in the same component style.
3. Draft reason/source and factual confirmation items are shown outside its body; final differences are computed from actual text.
4. Risk navigation has a bounded scroll area to keep the evidence and decision region available; real 1440×900 geometry remains unverified.
5. Exact detector offsets use Unicode code points; semantics use matching quotations, explicitly labelled without claiming model word coordinates.
6. Full V2 navigation uses existing Python page handlers. The independent entry explains that only the core review workspace is running.
7. An isolated Streamlit iframe may have parent padding/height differences. CSS similarity does not certify pixel fidelity.

No GPT Image generation, main/V5 edit, Codespace, merge or deployment occurred.
