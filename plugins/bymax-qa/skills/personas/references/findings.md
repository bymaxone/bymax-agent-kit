# Persona findings

The run exists to find everything a real person would hit, from a crash to a
label that wraps one letter per line. So the bar is not importance: a cosmetic
defect is reported at its own severity. The bar is **seen**: each finding is
something the persona met on a screen, with a screenshot, and a rule it
breaks.

## Classes

| Class | What it covers | Example |
| --- | --- | --- |
| `bug` | the app does the wrong thing: wrong data, wrong state, a crash, a lost write, a blank screen | the screen after a recorded miss shows only its header; a tap meant for "+" undoes the day's record because a toast sits over it |
| `flow` | the task can be done but the path is broken, long, or hidden | the required confirmation sits four scrolls below the button it unlocks, and the disabled button does not say where it is |
| `design` | layout, visual hierarchy, consistency, overlap, truncation | a title cut to "Separar os compri…" on the only place that names the item |
| `a11y` | the persona's settings break it: text size, contrast, target size, screen reader, motion | labels break mid-word at AX2; a layout switch that never turns on at Android font scale 1.3 because 1.3 arrives as 1.2999999523 |
| `copy` | wording that misleads, sentences assembled wrong, wrong language, a term that is not explained | the person's own words capitalised mid-sentence ("0 votos para Alguém que…"); a feature name nobody explains |
| `content` | the app says something wrong about the person's own case | a custom item narrated with another item's suggestions |
| `performance` | waits a person notices: a slow first screen, a frozen tap, a list that stutters | — |
| `privacy` | data shown to the wrong person, a scary or false privacy promise | — |

## Severity

| Band | Meaning |
| --- | --- |
| **Blocker** | the persona cannot complete a task the app exists for, or loses data |
| **Major** | the task needs a workaround most people in this persona would not find, or the result is wrong |
| **Minor** | the task completes with friction, confusion or a visible defect |
| **Polish** | cosmetic, noticed but not in the way |

Severity follows the consequence for this persona. When the same defect is
worse for another persona in the set, say so and grade it for the worse one.

## Admitting a candidate

Every oddity starts as a candidate in the day's journal. It becomes a finding
when all of these hold, each recorded in the finding:

1. **Seen.** A screenshot or recording shows it. A code reading may explain
   it, never stand in for it.
2. **Reproduced**, or unambiguous. Repeat the steps once from the screen
   before; a state that cannot be reached again (a day already past) needs a
   screenshot that shows it plainly, and the finding says it was seen once.
3. **Not the operator.** A slip of yours (two taps instead of one, a wrong
   field) is not a product defect. A slip the persona's limits make likely,
   and the app does not catch, is.
4. **Not the method.** A pinned clock out of order, a host that slept, a
   simulator glitch that does not repeat: record them in the journal as
   method notes, never as findings.
5. **Breaks a rule**, named: the app's spec or acceptance criteria (by id),
   a platform guideline (Apple HIG, Material, Android), a WCAG success
   criterion, or the plain expectation of this persona with the research
   line behind it.
6. **Not a decision.** Behaviour the spec chose on purpose and the persona
   dislikes is a product question: it goes to "Needs a human" with the
   persona's evidence, not to the findings.

## The finding file

Use `templates/finding.template.md` with these substitutions:

- `axis: persona`, and the class from the table above;
- **severity**: the band, no CVSS vector;
- **references**: the persona, the day and date, the screen, the rule broken
  (spec id, HIG/Material section, WCAG criterion);
- **component**: the screen and, only when you read the code, `path:line`
  marked "suspected";
- **reproduction**: the persona's settings, the state before, the steps as
  the persona did them, what they expected, what the screen showed;
- **evidence**: the screenshot paths under `personas/runs/P<n>/`;
- **impact**: what it costs this persona, in one or two sentences;
- **remediation**: the expected behaviour, and a fix direction only when the
  cause is plain; the owner decides how;
- **family**: the siblings seen on other screens, or "none seen".

Number findings `QA-NNN` in the shared registry, with `axis: persona` in the
row so audit and persona findings never read as each other.

## The persona report

`runs/P<n>/report.md` holds:

1. the persona, the build (commit, dirty count), the device and settings, the
   days run;
2. a table of findings: id, class, severity, day, screen, one line;
3. the coverage matrix rows this persona was meant to exercise, each marked
   exercised or not, with the reason;
4. method notes and operator slips, kept apart from the findings;
5. "Needs a human": product decisions with their evidence;
6. the declared limits (`time-travel.md` § What a pinned clock does not
   cover).
