# AI Reviewer Automated Acceptance Report

## Scope

This report covers the current V1 codebase after the automatic cover OCR and analysis flow update. The checks use temporary files and mocks where appropriate; they do not call DeepSeek or modify the production rule/history/profile files.

## Automated Coverage

| Area | Coverage |
|---|---|
| Rule management | Add a rule, verify it matches, disable it, verify it no longer matches, delete it, and verify it is removed. |
| Rule file resilience | Missing, empty, and malformed rule JSON returns a safe empty rule set. |
| Title safety | Generated title candidates are reviewed again; local safety rewrite removes remaining rule hits. |
| Rewrite cleanup | `数学思维` is rewritten once and never becomes `数理思维思维`. |
| Creator profile | Missing profile creates an empty template; saved context includes only recognized non-empty fields. |
| Local storage resilience | Malformed creator profile and history JSON return safe empty data. |
| Link importer | Invalid and localhost URLs return friendly errors; parser reads public metadata and ignores script text. |
| OCR resilience | Missing OCR dependency degrades safely; empty, English-only, repeated, symbol-heavy, and low-confidence OCR output is rejected. |
| Streamlit smoke test | Experience sample input persists after switching from workbench to cover diagnosis and back. |

## Executed Checks

```text
python3 -m py_compile app.py services/*.py tests/*.py
python3 -m unittest discover -s tests -v
```

Result: **13 tests passed**.

The current environment did not have a `pytest` executable. `pytest` has been added to `requirements.txt`; after installing dependencies, the suite can also run with:

```bash
pip install -r requirements.txt
pytest -q
```

## Automatic Cover Analysis Behavior

1. A cover file receives a SHA-256 fingerprint.
2. A new fingerprint clears the previous OCR and analysis state.
3. OCR runs once for the new file through `pytesseract` with `chi_sim+eng`.
4. OCR text is accepted only after quality checks for empty content, English-only output, repeated characters, excessive symbols, and low confidence.
5. Successful OCR automatically fills the editable cover text and triggers one DeepSeek cover analysis for that image.
6. The image fingerprint is recorded after the automatic attempt, including an API failure, so ordinary Streamlit reruns do not repeat OCR or consume additional API requests.
7. A user edit does not trigger analysis automatically. The user must choose **重新分析**, which intentionally analyzes the edited text once.

## Failure and Degradation Paths

- No image: cover page remains usable and prompts for upload.
- OCR dependency/Tesseract/Chinese language data unavailable: app starts normally, provides a clear message, and leaves the editable manual text field available.
- OCR returns unreliable text: the text is not used or displayed as a successful recognition result.
- Missing DeepSeek key or failed request: cover analysis displays the existing friendly error; the rest of the app continues to work.
- Invalid, private, or login-protected link: link import reports a friendly failure and manual analysis remains available.
- Missing or malformed local JSON: rules/history/profile services return safe empty data rather than crashing the page.

## Remaining Manual Verification

- Run OCR against a real Chinese cover after installing native Tesseract and `chi_sim` language data.
- Use a valid DeepSeek key to validate the actual automatic cover-analysis response and retry behavior.
- Upload two different cover images in a browser and visually confirm the first image's text and analysis disappear before the second result arrives.
- Verify browser clipboard permissions, real public-link import, and responsive behavior.

## Known Limits

- Current OCR is **Tesseract via `pytesseract`**, not a cloud OCR service. The Python package alone is insufficient: the native Tesseract executable and Simplified Chinese `chi_sim` data are required.
- Public-link import intentionally does not run JavaScript, follow redirects, bypass login, or handle captcha challenges.
- The test suite does not call external DeepSeek endpoints, so live API credentials, network conditions, and response quality remain manual integration checks.

## Deployment Assessment

There is no blocking startup or automated-test failure. The application can deploy without OCR installed because OCR is optional. To enable automatic Chinese cover recognition in deployment, install Tesseract and `chi_sim` in addition to `pip install -r requirements.txt`.
