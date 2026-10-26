# Working on this repository with a coding agent

A clone contains the code and project instructions. It does not contain another student's agent login, conversation history, Python environment, or ignored lab configuration. An agent account is separate from access to the robot and camera.

## Open the correct project

```bash
git clone https://github.com/Trylen22/lite6-lab-control.git
cd lite6-lab-control
```

Open this directory as the workspace in your coding tool, or start the installed `codex` or `claude` command from this directory. Sign in using your own account through the tool's normal setup. No project API key, shared login, special MCP server, or browser extension is required for ordinary repository editing and local checks.

The application itself uses the UFACTORY SDK and DepthAI. It does not need an LLM service or an agent running in the background.

## Load the project instructions

- **Codex:** the repository's `AGENTS.md` provides project instructions.
- **Claude Code:** `CLAUDE.md` imports `AGENTS.md` and this guide. Run `/memory` to inspect loaded instructions.
- **Other agents:** explicitly ask them to read these files before changing the project.

Verify that the agent can summarize the distinction between the Lab simulator and physical robot controls. Instruction files provide context; they are not a hardware interlock or a substitute for reviewing commands.

Official references: [Codex and AGENTS.md](https://developers.openai.com/codex/guides/agents-md/) and [Claude Code project instructions](https://code.claude.com/docs/en/memory).

## Start with a software-only task

Use this first prompt, then describe the change you want:

```text
Read AGENTS.md, README.md, docs/AGENT_SETUP.md, and docs/LAB_SETUP.md.
Explain the project structure and report what this clone is missing.
Work on the Lab simulator and offline tests first. Do not operate the arm,
start physical demos, change device networking, or copy another station's
calibration. Use the simulator example configuration and the /#lab URL.
Show the change and validation results before proposing a hardware trial.
```

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-deck.txt
.venv/bin/python -m unittest discover -s tests -v
node --check assets/app.js
.venv/bin/python -m labdeck.server --config config/lab.simulator.example.toml
```

Open `http://127.0.0.1:8100/#lab`. Choose an example and press Run in the Lab panel. Stop the local server with Ctrl+C. The observer is pointed at loopback, so missing robot and camera telemetry is expected. This configuration is for the Lab preview; it does not disable all physical routes if an existing `local/lab.toml` is present.

Node.js is used for the optional JavaScript syntax check. The Lab page also needs browser access to its external JavaScript libraries and model assets. See [third-party references](THIRD_PARTY.md).

## Connect to the shared station separately

Follow [Lab setup](LAB_SETUP.md) for the actual robot and camera addresses, the host's two subnets, and local configuration. A friend using the same station can reuse its documented network addresses after confirming the equipment. That does not recreate the station's taught motion profiles.

The ignored local files include:

| File | Purpose |
|---|---|
| `local/lab.toml` | Runtime device addresses |
| `local/automation.json` | Tabletop pickup calibration and workspace profile |
| `local/hand-follow.json` | Wrist hand-follow calibration |
| `local/start-poses.json` | Taught demo start joints |
| `local/shelf-place.json` | Taught shelf-transfer waypoints |
| `local/taught_poses/` | Contact references and controller/tool records |
| `local/lab-kinematics.json` | Optional per-arm simulator kinematic fit |

A fresh clone does not need these motion profiles to view the Lab simulator. Physical demonstrations need the applicable validated files and a supervised station handoff. Ask the station owner which files still match the current mounting, tool, and workspace; do not invent missing values to make a button run. Models are downloaded through the explicit scripts described in the README.

## Review and contribute

Use a branch for a proposed change:

```bash
git switch -c lab/my-change
```

Keep source comments educational: explain units, frames, controller return values, and why a check exists. Run checks appropriate to the change, inspect `git diff`, and confirm that `local/`, credentials, and recordings are not staged. A collaborator without push permission can fork the repository and open a pull request; an agent login does not grant GitHub repository permission.

Historical trial authorizations in `AGENTS.md` and the session log describe earlier supervised work. They do not establish that an operator is present in a new session or authorize a new collaborator to move the robot.
