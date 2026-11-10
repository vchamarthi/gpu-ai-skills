<!--
Copyright (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Free check for your AI skills: a 5-minute guide

**For:** anyone who owns a repository of AI "skills" (how-to pages your AI helper reads).
**Cost:** free. No AI model is called, no account, no key.
**Time:** about 5 minutes to try, 10 to switch on for every change.

---

## The one-minute idea

Your skills are written once and then trusted. Nobody notices when one of them
is broken, confusing, or risky, until your AI helper quietly ignores it or does
the wrong thing.

This check reads every skill, the way a spell-checker reads a document, and
tells you what is wrong **before** anyone installs it.

---

## Try it now (3 steps)

1. Install the tested version (the plain `pip install dokimi` is an older release without these checks):

   ```bash
   pip install "dokimi @ git+https://github.com/intel/dokimi@b30a1a200ceb126b0e9cd3c9c7ea34019981db6c#subdirectory=dokimi"
   ```
2. Point it at your skills folder:

   ```bash
   dokimi catalog check --root path/to/your-repo --kind skills
   ```

3. Read the list. Each skill says **ok** or **warn**, with a plain sentence
   saying what to fix.

Nothing is changed in your repo. It only reads.

---

## What it catches: six real situations

Each one below is something the check found. The first four skills are made up
to show the pattern; the "real" lines are from a scan of the public
`intel/skills` and `intel/gpu-ai-skills` repositories.

### 1. A skill that is silently dead

> **What happened:** Someone wrote `description: Use when: writing release notes`.
> The extra colon breaks the file. The AI helper cannot read the skill, and
> nothing tells anyone.
>
> **What the check says:**
> `ERROR: this skill has invalid text at the top; put the description in quotes`
>
> **Why you care:** A skill nobody can load is wasted work.

### 2. Two skills that fight each other

> **What happened:** `gpu-profiler` and `gpu-profiling-helper` say almost the
> same thing. The AI helper picks one at random.
>
> **What the check says:**
> `these two descriptions overlap 100%; the model may pick either`
> and suggests merging them.
>
> **Real example:** `sglang-xpu-bench` and `vllm-xpu-bench` are flagged as
> possible merge candidates.

### 3. A skill that never gets picked

> **What happened:** The description says "Tunes kernels." The AI helper
> chooses a skill by reading only that line. It has no idea *when* to use it.
>
> **What the check says:**
> `description has no 'when' clause (e.g. 'use when ...')`
>
> **Real example:** 4 of 35 skills in `intel/skills` and 3 of 22 in
> `intel/gpu-ai-skills` (`vllm-xpu-run`, `vllm-xpu-profile`, `xpu-discover`).
>
> **Fix:** start the description with "Use when ...".

### 4. A skill that tells the AI to run unknown code

> **What happened:** A skill says to download a script and run it in one go.
> If that website is ever hacked, your users' machines run the attacker's code.
>
> **What the check says:**
> `a download is piped into a shell; save the file, read it, then run it`
>
> **Real example:** `vllm-xpu-bench` and `sglang-xpu-bench`, in both repos.

### 5. A skill that installs "whatever is newest"

> **What happened:** The skill says `pip install torch` with no version. It
> works today. In six months a new release breaks it and nobody knows why.
>
> **What the check says:**
> `installs name no version; pin each as pkg==1.2.3`
>
> **Real example:** 6 skills in `intel/skills` (one lists 24 such installs)
> and 3 in `intel/gpu-ai-skills`.

### 6. A skill that points to a page that is not there

> **What happened:** The skill says "see the metrics guide" and links a file
> that was never added. The AI helper gets stuck or guesses.
>
> **What the check says:**
> `link 'references/metrics.md' names no file`

---

## The result, in one picture

What the scan of the two real repositories said:

| Repository | Skills checked | Fine | Need a look | Broken |
|---|---|---|---|---|
| `intel/skills` | 35 | 23 | 12 | 0 |
| `intel/gpu-ai-skills` | 22 | 14 | 8 | 0 |

Nothing is broken. All of it is small, fixable, and was invisible before.

---

## How you see what needs attention

- **One list:** every skill on one line, `ok`, `warn` or `ERROR`, with plain words under each one.
- **On every change:** the same list is in the run log and on the run's summary page.
- **For tools:** add `--format json` to feed a dashboard or script.

| Level | Meaning | Effect |
|---|---|---|
| Red, `ERROR` | The skill cannot load | The change is marked failed |
| Yellow, `warn` | Worth a look | A note only; the change still passes |

Warnings never fail the check, so they show in the log or summary, not as a mark on the change.

---

## What to fix, and how

| The check says | Level | What to do |
|---|---|---|
| Invalid text at the top (`frontmatter-parse`) | Red | Put the description in quotes |
| No "use when" line (`description-no-when`) | Yellow | Start the description with "Use when ..." |
| Near-duplicate skill (`description-near-duplicate`) | Yellow | Merge the two, or reword one to differ |
| Download piped to a shell (`pipe-to-shell`) | Yellow | Save the file, read it, then run it |
| Install with no version (`install-unpinned`) | Yellow | Pin it, for example `pkg==1.2.3` |
| Link to a missing file (`link-missing`) | Yellow | Add the file or fix the link |
| Skill page too long (`body-too-large`) | Yellow | Move detail into bundled files |

The check only reports. You make the fix, then run it again. Disagree with a
warning? Silence it with `--ignore <code>`.

---

## More free checks, beyond skills

All three are free and run on your own checkout. The real results below are from a
scan of `intel/gpu-ai-skills`.

| Command | What it does | Real result |
|---|---|---|
| `dokimi repo scan .` | Checks that files, commands and links named in `AGENTS.md` and `CLAUDE.md` really exist | 40 claims: 29 ok, 10 undecided, 1 wrong. `AGENTS.md` line 60 names `scripts/publish.sh`, which is not there |
| `dokimi repo budget .` | Shows how much text the AI helper loads at the start, and what it skips | 6,492 characters loaded. `CLAUDE.md` switches `AGENTS.md` off, so 17,509 more sit unread unless opened |
| `dokimi skill check NAME --root .` | The same skill checks, for just the skill you are editing | `xpu-discover`: no "use when" line |

---

## Make it automatic (so nobody has to remember)

This repository already has `.github/workflows/skills-check.yml` (a simplified version is shown below). Every change to a skill is checked, and a problem shows up as a red mark on
the change before it is merged.

```yaml
name: Skills check
on:
  pull_request:
    paths: ['**/SKILL.md', 'skills/**']
permissions:
  contents: read
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: intel/dokimi/actions/setup@b30a1a200ceb126b0e9cd3c9c7ea34019981db6c
        with:
          dokimi-ref: b30a1a200ceb126b0e9cd3c9c7ea34019981db6c
      - run: dokimi catalog check --root . --kind skills --strict
```

The setup step is pinned to one exact dokimi version, so the check never changes under you.


Five free checks run on every change (all verified in real runs in both forks):

| Check | Fails the change? | Real result |
|---|---|---|
| 1. Skills check | Only if a skill cannot load | `intel/skills`: 35 skills, 23 ok, 12 warn, 0 error |
| 2. Static plan, every skill | No | Both repos: pass |
| 3. Instruction files scan | No | `gpu-ai-skills`: 40 claims, 1 wrong |
| 4. Instruction size | No | `gpu-ai-skills`: 6,492 characters at start |
| 5. Agent setup check | No | `intel/skills`: no `AGENTS.md` or `CLAUDE.md` at the root |

Results appear in the run summary and in a downloadable report.

**Red mark = a skill could not be loaded or breaks the skill format.**
Everything else is shown as a yellow note and does not block the change.

---

## Who this is for

| You are | What you get |
|---|---|
| **Owner of a vendor skills repository** (for example `intel/skills`, `intel/gpu-ai-skills`) | A clean report before each release; fewer "your skill did nothing" complaints |
| **A team keeping agent instructions** (`AGENTS.md`, rules, skills) next to code | A guard so a hasty edit cannot break what the AI helper reads |
| **Anyone reviewing a skill someone else sent** | A 10-second safety and quality screen before installing it |

---

## What this check does not tell you

It tells you a skill is **well-formed and safe to load**. It does not tell you
whether the skill **actually makes the AI better**. That is the next step, it
uses an AI model (so it costs money), and dokimi runs it as a before-and-after
test. Start with the free check; add the paid test only for the skills that
matter most.

---

## What the free check does not do yet

- **Fixes are manual:** it reports, you edit, then run it again.
- **Warnings are quiet:** they show in the log and summary, not as a mark on the change.
- **Your skills only:** twins and "which one gets picked" are judged among your own skills.
- **Facts are not checked:** it cannot tell whether a skill's advice is true or out of date.
- **"Does it help?"** needs the paid before-and-after test.

---

## Questions you may have

| Question | Answer |
|---|---|
| Does it cost anything? | No. No AI model, no account, no key. |
| Will it change my files? | No. It only reads and reports. |
| Do I need to code? | One copy-paste line, or none once the automatic check is on. |
| How long does it take? | About a minute to set up on GitHub, then a few seconds for the checks. |
| Can I ignore a warning? | Yes. Add `--ignore` with the warning's code. |
| Does "ok" mean it is good? | No. It means well-formed and safe to load, not better answers. |

---

## If something looks wrong

- A warning you disagree with: leave it out with `--ignore <code>` (the code is
  the word after "warn", for example `install-unpinned`).
- Want it as a file for a dashboard: add `--format json`.
- The full list of what is checked: dokimi docs, `external-content.md`,
  section "Scan the checkout before you spend anything".
