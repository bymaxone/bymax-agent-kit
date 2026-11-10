# Research — who would use this app

The personas are only as good as the evidence under them. This step finds who
uses apps like this one, why they stop, what they praise, what they cannot
do, and what the platform standards require for them. Read sources directly;
when a primary source cannot be opened, say so on that line.

## Evidence labels

Every claim in `research/research.md` carries one:

| Label | Means |
| --- | --- |
| `[peer-reviewed]` | a journal or conference paper, with authors, venue, year and sample size |
| `[official]` | a platform guideline (Apple HIG, Material, Android developers), a standard (W3C WCAG), a government statistics office |
| `[survey]` | a sample survey with published method; a non-scientific poll is labelled as such |
| `[industry]` | an analytics or market report (StatCounter, Sensor Tower, RevenueCat) |
| `[listing]` | what an app's store listing, site or help center claims about itself |
| `[user voice]` | a store review or forum post, quoted as written |
| `[inferred]` | your inference from the above, to be validated |

Numbers are written as the source writes them, with the year and the sample.
A figure found only in the press, or attributed to a source that does not
contain it, goes on the **do-not-cite** list at the end of the file with the
reason.

## Order of work

1. **Reuse first.** Read the project's own research (`docs/research/`, the
   spec's audience section, prior store-review corpora). Say which files you
   reused and only fill what they lack.
2. **The audience.** Who uses this category of app, by age, platform and
   income where data exists; why they adopt and why they abandon. Prefer
   peer-reviewed studies and national statistics of the target markets (in
   Brazil: IBGE, Cetic.br TIC Domicílios; elsewhere the national equivalent).
3. **Specific groups.** The groups the category's users and the app's spec
   point to: older adults and presbyopia, low vision, ADHD and executive
   function, shift workers, caregivers, students, people on limited data
   plans, people sharing a phone. Name a gap where no study exists rather than
   filling it with an inference.
4. **Platform requirements.** The numeric guidance a persona will test:
   - Apple HIG Typography and Accessibility: Dynamic Type sizes, minimum
     control size;
   - Android: touch target size, `sp` text following the font scale;
   - WCAG 2.2: 1.4.3 contrast, 1.4.4 resize text, 1.4.10 reflow, 2.5.8
     target size.
   Read the current page, not a summary of it, and record the date read.
5. **Competitors in the stores.** Below.
6. **Forums.** Reddit, Hacker News and the target country's communities, on
   the category's pains. Quote with the URL. When a site cannot be fetched
   from here, say so and use the archived evidence the project already holds.

## Competitor stores

The App Store has public endpoints; Google Play does not publish reviews
through an API. `persona-store-reviews.py` covers the App Store and records
every request it makes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/persona-store-reviews.py" discover \
  --out .claude/qa/personas/research/stores \
  --countries br us --terms "habit tracker" "hábitos"
```

`discover` runs the iTunes Search API for every term × country and ranks apps
by how often and how high they appear (`discovery.json`). Pick the competitors
with the human (interview round 2), then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/persona-store-reviews.py" reviews \
  --out .claude/qa/personas/research/stores \
  --countries br us --pages 3 --apps 1111447047 963034692
```

`reviews` reads each app's listing (`lookup.json`: rating, rating count,
price, version, languages) and its most recent reviews from Apple's public
review feed, per storefront, into `reviews.json`. An
empty page is retried with a growing pause, since the feed answers an empty
page both when it rate-limits and when there are no more reviews; every
attempt is a line in `collection-log.tsv`. Reviewer names are dropped.

Google Play: read each competitor's listing page with `WebFetch`
(`https://play.google.com/store/apps/details?id=<package>&hl=en&gl=<country>`)
for installs, rating and the review count it shows. Record that Play reviews
were not collected in bulk.

### Reading the reviews

The corpus is read, not only counted:

1. Read every low-rated review (1–3 stars) longer than about 100 characters
   in the target markets' languages.
2. Read every review that mentions the category's known pains (for a habit
   app: streak, missed day, reminder, notification; for a shop: checkout,
   delivery, refund).
3. Read samples of the other themes: onboarding, design, text size,
   accessibility, privacy, price, and some long 5-star reviews for what people
   value.
4. Count themes with keyword rules in each language, and check each rule's
   precision by reading ten matches it picked. Report the count with that
   precision.

A theme rare in reviews is not a rare need: people who cannot read an app
often leave without writing. Say so where it applies.

## Using agents

Deep research can run on three fronts at once. Spawn at most three
`general-purpose` agents, each with one front and the same contract:

- the audience, specific groups and platform requirements;
- the competitor stores (run the collector, read the corpus as above);
- the forums and community voices.

Each returns claims with their label and URL, quotes as written, and its own
gaps. You check every claim the personas will rest on before using it; a
claim you could not check is labelled `[inferred]` or dropped.

## What `research/research.md` holds

1. Method: sources, dates, what was reused, what could not be read.
2. Segments with sources (a table: finding, source, label).
3. Real cases and quotes (a numbered table, Q1…Qn, each with its source).
4. Specific groups, and the platform requirements with their numbers.
5. Design implications, marked `[inferred]`.
6. Gaps, and the do-not-cite list.
