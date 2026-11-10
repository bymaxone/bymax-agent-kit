#!/usr/bin/env python3
"""Collect App Store evidence about competing apps for persona research.

Layer: plugin helper script of /bymax-qa:personas (the research step). It reads
Apple's public endpoints only: the iTunes Search API to discover apps, the
Lookup API for each listing, and the customer-review feed for recent reviews.
Every request is a line in collection-log.tsv, reviewer names are never stored,
and nothing is written outside the --out directory.

Usage:
  persona-store-reviews.py discover --out DIR --countries br us --terms "habit tracker"
  persona-store-reviews.py reviews  --out DIR --countries br us --apps 1111447047 [--pages 3]
"""
import argparse
import datetime
import http.client
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SEARCH = 'https://itunes.apple.com/search?'
LOOKUP = 'https://itunes.apple.com/lookup?'
FEED = 'https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app}/sortby=mostrecent/json'
MAX_PAGES = 10
COUNTRY = re.compile(r'^[a-z]{2}$')
APP_ID = re.compile(r'^[0-9]{1,12}$')
USER_AGENT = 'bymax-qa-personas/1.0'
RETRY_STATUS = {0, 403, 429, 500, 502, 503, 504}


def http_get(url, timeout):
    """One GET; returns (status, body bytes), status 0 when no response came back."""
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b''
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError):
        return 0, b''


class Client:
    """Fetches JSON with retries and logs every attempt to a TSV file."""

    def __init__(self, log_path, fetch=http_get, sleep=time.sleep, retries=4, pause=2.0, timeout=20):
        self.log_path, self.fetch, self.sleep = log_path, fetch, sleep
        self.retries, self.pause, self.timeout = retries, pause, timeout

    def log(self, url, attempt, status, size, note):
        """Append one request attempt to the TSV log."""
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        with open(self.log_path, 'a', encoding='utf-8') as handle:
            handle.write(f'{stamp}\t{url}\t{attempt}\t{status}\t{size}\t{note}\n')

    def get(self, url, empty=lambda payload: False):
        """The parsed JSON at url, or None. An `empty` payload is retried like a refusal."""
        payload = None
        for attempt in range(1, self.retries + 2):
            status, body = self.fetch(url, self.timeout)
            try:
                payload = json.loads(body) if status == 200 else None
            except ValueError:
                payload = None
            if payload is not None and not empty(payload):
                self.log(url, attempt, status, len(body), 'ok')
                return payload
            if status == 404:
                self.log(url, attempt, status, len(body), 'not found')
                return None
            retry = attempt <= self.retries and (status in RETRY_STATUS or status == 200)
            self.log(url, attempt, status, len(body), 'empty, retrying' if retry else 'empty')
            if not retry:
                return payload
            self.sleep(self.pause * attempt)
        return payload


def checked(values, pattern, what):
    """Values that will enter a URL, refused unless each matches its pattern."""
    for value in values:
        if not pattern.match(value):
            raise SystemExit(f'error: {what} {value!r} is not valid')
    return values


def search(client, term, country):
    """Search results for one term in one storefront."""
    query = urllib.parse.urlencode({'term': term, 'country': country, 'entity': 'software', 'limit': 50})
    payload = client.get(SEARCH + query) or {}
    return payload.get('results', [])


def discover(client, terms, countries):
    """Apps ranked by how often and how high they appear across terms and storefronts."""
    apps = {}
    for term in terms:
        for country in countries:
            for rank, result in enumerate(search(client, term, country), start=1):
                app_id = str(result.get('trackId', ''))
                if not app_id:
                    continue
                entry = apps.setdefault(app_id, {
                    'id': app_id, 'name': result.get('trackName', ''), 'seller': result.get('sellerName', ''),
                    'appearances': 0, 'best_rank': rank, 'countries': [], 'terms': [], 'rating_count': 0})
                entry['appearances'] += 1
                entry['best_rank'] = min(entry['best_rank'], rank)
                entry['rating_count'] = max(entry['rating_count'], int(result.get('userRatingCount') or 0))
                for key, value in (('countries', country), ('terms', term)):
                    if value not in entry[key]:
                        entry[key].append(value)
    return sorted(apps.values(), key=lambda entry: (-entry['appearances'], entry['best_rank'], entry['id']))


def lookup(client, app_id, country):
    """The listing summary of one app in one storefront, or None."""
    payload = client.get(LOOKUP + urllib.parse.urlencode({'id': app_id, 'country': country})) or {}
    results = payload.get('results') or []
    if not results:
        return None
    item = results[0]
    return {
        'name': item.get('trackName'), 'seller': item.get('sellerName'),
        'rating': item.get('averageUserRating'), 'count': item.get('userRatingCount'),
        'price': item.get('formattedPrice'), 'version': item.get('version'),
        'released': item.get('releaseDate'), 'updated': item.get('currentVersionReleaseDate'),
        'languages': item.get('languageCodesISO2A'), 'genre': item.get('primaryGenreName'),
        'url': item.get('trackViewUrl'), 'min_os': item.get('minimumOsVersion'),
    }


def feed_entries(payload):
    """The review entries of one feed page; the feed sends a lone entry as an object."""
    entries = (payload.get('feed') or {}).get('entry') or []
    if isinstance(entries, dict):
        entries = [entries]
    return [entry for entry in entries if isinstance(entry, dict) and 'im:rating' in entry]


def label(entry, key):
    """The `label` of one feed field, or an empty string."""
    value = entry.get(key)
    return value.get('label', '') if isinstance(value, dict) else ''


def review_record(entry, app_id, app_name, country):
    """One review as stored: no reviewer name, no profile link."""
    return {
        'app': app_id, 'appName': app_name, 'storefront': country, 'reviewId': label(entry, 'id'),
        'date': label(entry, 'updated'), 'rating': int(label(entry, 'im:rating') or 0),
        'title': label(entry, 'title'), 'content': label(entry, 'content'), 'version': label(entry, 'im:version'),
    }


def reviews_of(client, app_id, app_name, country, pages):
    """The most recent reviews of one app in one storefront, page by page until one is empty."""
    found = []
    for page in range(1, pages + 1):
        url = FEED.format(country=country, page=page, app=app_id)
        payload = client.get(url, empty=lambda body: not feed_entries(body)) or {}
        entries = feed_entries(payload)
        if not entries:
            break
        found += [review_record(entry, app_id, app_name, country) for entry in entries]
    return found


def read_json(path, default):
    """A JSON file's content, or the default when it does not exist yet."""
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path, value):
    """Write value as indented UTF-8 JSON."""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def collect_reviews(client, out, apps, countries, pages):
    """Listings into lookup.json and reviews merged into reviews.json; returns counts per app and country."""
    listings = read_json(out / 'lookup.json', {})
    merged = {review['reviewId']: review for review in read_json(out / 'reviews.json', [])}
    counts = {}
    for app_id in apps:
        for country in countries:
            listing = lookup(client, app_id, country)
            stored = listings.setdefault(app_id, {})
            if listing is not None or stored.get(country) is None:
                stored[country] = listing
            name = (listing or {}).get('name') or ''
            found = reviews_of(client, app_id, name, country, pages) if listing else []
            counts[(app_id, country)] = len(found)
            merged.update({review['reviewId']: review for review in found if review['reviewId']})
    write_json(out / 'lookup.json', listings)
    ordered = sorted(merged.values(), key=lambda r: (r['app'], r['storefront'], r['date'], r['reviewId']))
    write_json(out / 'reviews.json', ordered)
    return counts


def parse(argv):
    """The command line, with every value that enters a URL validated."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='mode', required=True)
    commands = {}
    for mode in ('discover', 'reviews'):
        command = commands[mode] = sub.add_parser(mode)
        command.add_argument('--out', required=True, type=pathlib.Path)
        command.add_argument('--countries', nargs='+', required=True)
        command.add_argument('--retries', type=int, default=4)
        command.add_argument('--pause', type=float, default=2.0)
    commands['discover'].add_argument('--terms', nargs='+', required=True)
    commands['reviews'].add_argument('--apps', nargs='+', required=True)
    commands['reviews'].add_argument('--pages', type=int, default=3, choices=range(1, MAX_PAGES + 1))
    args = parser.parse_args(argv)
    args.countries = checked([c.lower() for c in args.countries], COUNTRY, 'country')
    if args.mode == 'reviews':
        args.apps = checked(args.apps, APP_ID, 'app id')
    return args


def main(argv=None, fetch=http_get, sleep=time.sleep):
    """Run one mode; fetch and sleep are injectable so the tests reach no network."""
    args = parse(sys.argv[1:] if argv is None else argv)
    args.out.mkdir(parents=True, exist_ok=True)
    client = Client(args.out / 'collection-log.tsv', fetch, sleep, args.retries, args.pause)
    if args.mode == 'discover':
        ranked = discover(client, args.terms, args.countries)
        write_json(args.out / 'discovery.json', ranked)
        for entry in ranked[:20]:
            print(f"{entry['id']}\t{entry['appearances']}\t#{entry['best_rank']}\t{entry['rating_count']}\t{entry['name']}")
        print(f'{len(ranked)} apps in {args.out / "discovery.json"}')
        return 0
    counts = collect_reviews(client, args.out, args.apps, args.countries, args.pages)
    for (app_id, country), count in sorted(counts.items()):
        print(f'{app_id}\t{country}\t{count}')
    print(f'{sum(counts.values())} reviews read; corpus in {args.out / "reviews.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
