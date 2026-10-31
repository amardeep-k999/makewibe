# GitHub push order

Repository: https://github.com/amardeep-k999/makewibe
Branch: main

| Order | Owner | Folder | Contents |
|---|---|---|---|
| 01 | Amok | 01_foundation/project | Entry point, database, helpers, requirements, README |
| 02 | Aadish | 02_business_logic/project | Accounts, catalog, subscriptions, billing, payments, reports, email |
| 03 | Amok | 03_interface/project | HTML templates, CSS and icon |
| 04 | Aadish | 04_tests_and_handoff/project | Tests, launchers, guides, final README |

Copy the CONTENTS of each project folder into the repository ROOT, preserving nested file paths. Do not upload the owner, numbered-step or project wrapper folders.

Pull main before every stage. Stage only the files assigned to that stage. Push normally; never force-push. Preserve original client.py and server.py and unrelated changes. Wait for the previous stage to appear on main before continuing. Intermediate commits are intentionally partial; run the app after stage 04.

Commit messages:
1. Add application foundation and update project README
2. Add subscription billing and account workflows
3. Add web interface and responsive styling
4. Add tests, launchers and project documentation

After stage 04, install requirements-dev.txt in a virtual environment and run python -m pytest -q. Start with START.bat on Windows. Never commit instance folders, databases, email outboxes, secrets or virtual environments.
