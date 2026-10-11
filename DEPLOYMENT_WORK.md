# ChatGPT deployment work

Working branch: `feat/chatgpt-deployment`.
Base: `e22db50` (local public repository snapshot).

Scope: HTTP deployment adapter, deployment smoke checks, and a plugin package builder.
Generated `tax_server.py` and tax calculation rules are not edited by this work.
Public hosting and platform submission are not complete until verified separately.

Verified on 2026-10-11 (Asia/Seoul):
- `py -X utf8 scripts/check_chatgpt_http.py`: PASS. Real loopback HTTP initialization,
  39 advertised tools without LAW_OC, 5 successful synthetic calls, 3 invalid/disabled
  calls rejected, invalid Host rejected, configured domain challenge served.
- `py -m pytest tests -q -p no:cacheprovider`: 56 passed.
- Public HTTPS origin accepted; non-HTTPS origin rejected.
- `git diff --check`: no whitespace errors.

Not performed: Docker image build (Docker unavailable here), internet deployment,
ChatGPT dialogue tests, independent tax correctness audit, publisher verification,
policy-page publication, demo recording, platform submission or approval.
The package builder needs real endpoint/publisher/policy/demo values before making
a submission ZIP. `plugin/review-cases.json` contains proposed dialogue checks,
not claims that those dialogues have run successfully.
