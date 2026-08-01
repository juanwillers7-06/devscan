# devscan

Scan `~/dev` for git projects and keep the Hermes project dashboard in sync.

## Why

The project dashboard (`/projects` quick command) reads a static registry at
`~/.hermes/scripts/projects.json`. Hand-editing it every time a new project
appears is boring and forgettable. `devscan` looks at what's actually in
`~/dev/` and regenerates the dev entries for you.

## Usage

```bash
devscan              # preview — show what would be synced
devscan --sync       # scan and write registry changes
devscan --json       # machine-readable output
```

Dev-scanned entries are tagged `"source": "devscan"` so they never clobber
hand-managed entries (Flip Crew, Cost Efficiency, etc.).

## How it works

1. Lists directories under `~/dev/` that contain a `.git` folder
2. For each: reads last-commit status (active ≤ 30 days, else paused),
   and a one-line description from README or the latest commit message
3. Merges into the registry, preserving non-devscan entries

## Install

```bash
ln -s ~/dev/devscan/devscan.py ~/.local/bin/devscan
chmod +x ~/dev/devscan/devscan.py
```
