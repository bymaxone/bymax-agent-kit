# Personas, failure scripts and coverage

A persona is a tool for exercising the app the way a kind of person would. It
is an inferred composite: no real person, an invented name marked as such,
every trait traceable to a line of the research. The set is judged by what it
makes the app do, so the coverage matrix matters as much as the profiles.

## The profile

Write each persona in `personas/personas.md` with these fields:

| Field | Content | Example |
| --- | --- | --- |
| id and name | `P<n>`, an invented name, age, city, occupation | P4 — Lúcia (invented), 63, Porto Alegre, retired teacher |
| device | the model class, OS, and the exact settings the run will apply | iPhone SE class, iOS Larger Text AX2 with Bold Text, light theme with Increase Contrast |
| abilities and limits | vision, motor, attention, language, connectivity, patience, each with the research line it rests on | presbyopia and early cataract (research §3.1); sometimes uses VoiceOver |
| routine | the day the app has to fit into | home at 07:00, walk after breakfast, lunch at 12:00 |
| motivation | why they installed it, in their words, from a real quote where one fits | "wants something forgiving" (Q7) |
| what they will do | the concrete content they will enter: items, names, amounts, habits, with the wording a person like them would type | "Separar os comprimidos da manhã", minimum "pôr a caixinha na mesa" |
| failure script | what goes wrong for them during the simulated span, by day | day 9–11 child sick, nothing logged; day 12 back through recovery |
| flows they exercise | the app's flows this persona reaches | onboarding at large text, edit, export, erase all |
| sources | the research ids the profile rests on | D14, Q21, Q22, §3.3 |

The content a persona types is part of the test. Write it the way they would:
a capital first letter, a typo they would make, a long name that does not fit,
an accent, an emoji, a value at the edge of what the field takes. Several of
the defects a persona run finds come from that text meeting a sentence
template.

## The failure script

Real use is mostly days where something gets in the way. Give each persona,
across the span, at least:

- a stretch of missed days with an outside cause (illness, travel, a deadline);
- a recovery after it, through whatever the app offers for coming back;
- a change of routine that asks them to edit something they set up;
- one slip of the kind their limits make likely (a tap on the wrong control,
  a sheet closed by accident, a field left half filled);
- the app's periodic moments: a weekly or monthly screen, a reminder, an offer;
- one moment of doubt about privacy or data (another person on the phone, a
  phone swap, export before a repair, erase all).

Add what the category makes specific: for a shop, a cart left overnight and a
refund; for a finance app, a month boundary and a currency; for a habit app,
a log after midnight. Mark each event with its day.

## Mixing the set

Across the set, vary what changes how an app behaves:

- platform, and within it a small and a large screen;
- text size: the default, early presbyopia (Android 1.3, iOS a size or two up),
  and an accessibility size (Android 2.0, iOS AX2 or larger);
- light and dark theme, Reduce Motion, a screen reader for at least the main
  screens;
- language, when the app ships more than one, including a switch mid-span;
- time zone and the local day boundary, when anything in the app is dated;
- connectivity: offline onboarding, a data plan that runs out;
- tech comfort: one persona who reads nothing and taps fast, one who reads
  everything and is afraid to break something.

## The coverage matrix

List every flow the app has (from its routes, screens and spec), then which
personas exercise it:

| Flow | Personas |
| --- | --- |
| Onboarding (offline, fast, large text) | P1, P3, P4 |
| … | … |

Every flow needs at least one persona; a flow the users depend on daily
needs two on different platforms or text sizes. A flow no persona reaches is
named under the matrix as uncovered, with the reason, and offered to the human
as a reason to add or adjust a persona.

## Order

Run the persona most likely to break the app first: usually the strongest
accessibility settings on the smallest screen. Its findings are fixed before
the gentler personas run, so they do not report the same defects again.

## Approval block

`personas.md` ends with:

```
approved-by:
approved-on:
notes:
```

Leave `approved-by:` empty until the human approves the set in this session;
the plan refuses to start without it.
