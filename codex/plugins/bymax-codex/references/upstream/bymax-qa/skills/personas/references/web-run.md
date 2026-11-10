# Running a persona in a browser

How to reach a web app is always asked (interview round 3): where it runs,
which browser drives it, how a persona signs in, how time moves, which
viewports. This reference covers what to do with each answer.

## Preflight

| Check | How you know | On failure |
| --- | --- | --- |
| the app is up | the URL from the plan answers in the browser with the app's first screen | start it with the repository's dev script, or stop and say which host did not answer |
| the host is not production | the plan's host is `localhost`, a staging or preview host the human named | refuse |
| the driver is available | Browser pane: the session exposes its preview tools; `agent-browser --version`; Playwright: the project's config and `@playwright/test` installed | offer `/bymax-web-verify:setup` for `agent-browser` |
| a clean user | a new registration, or a named test account reset by the human | a persona never inherits another persona's data |

## Drivers

- **Claude Browser pane** (the human watches): navigate, read the page,
  click, type, screenshot, through the pane's tools. Best for interactive
  days.
- **`agent-browser`**: `open <url>`, `snapshot` (the accessibility tree with
  element refs), `click`, `fill`, `screenshot`, `console`, `errors`, `close`.
  The snapshot is what you read before each action; console and page errors
  are read after every state change, since an error there is a finding even
  when the page looks right.
- **The project's Playwright**: for scripted days and for moving time. Write
  one spec per simulated day under the workspace and run them one at a time,
  in order, with the project's own runner; never as one parallel suite, which
  breaks the day order.

In every driver, act through what the persona sees: links and buttons by
their visible text or accessible name, never by a CSS selector they could not
perceive, never by calling the API behind the page.

## Persona settings in a browser

| Persona need | How |
| --- | --- |
| a phone or tablet | the viewport from the plan, with touch where the driver supports it |
| large text | WCAG 1.4.4: browser zoom to 200%, or the equivalent viewport (a 1280-wide layout at 200% behaves as 640 wide) |
| reflow | WCAG 1.4.10: a 320 CSS px wide viewport; content must not need horizontal scrolling |
| dark theme | `prefers-color-scheme: dark` (Playwright `colorScheme`, or the browser's setting) |
| Reduce Motion | `prefers-reduced-motion: reduce` (Playwright `reducedMotion`) |
| keyboard-only | Tab, Shift+Tab, Enter and Space only; record where focus is lost or invisible |
| a screen reader | read the accessibility tree for names, roles and order; a control with no name is a finding |

## Time

Use the clock the plan chose: the app's own dev clock, or Playwright's clock
control after confirming it in the installed declarations. Pin the day at the
start of each spec. Without either, run same-day sessions and mark multi-day
flows as not exercised.

## What else to read on every screen

- console errors and failed network requests (the page can look fine);
- the tab title and the URL after navigation (a back button that loses state);
- a reload in the middle of a form (what a distracted person does);
- the browser's back button after a submit (a duplicate order, a lost draft).
