#!/usr/bin/env python3
"""Write one Maestro flow per simulated day of a persona, from a compact day plan.

Layer: plugin helper script of /bymax-qa:personas (scripted days of a mobile run).
Each day pins the app's clock through the config's pin flow, screenshots the
screen, performs the day's actions in the order the screen lists the pending items,
and screenshots again. The config format is in skills/personas/references/mobile-run.md.

Usage: persona-days.py <config.json> <out-dir>
"""
import datetime
import json
import pathlib
import re
import sys

LETTER = re.compile(r'^[A-Z]$')
STAMP = re.compile(r'^\d\d:\d\d$')
OFFSET = re.compile(r'^(Z|[+-]\d\d:\d\d)$')
REQUIRED = ('appId', 'persona', 'first_date', 'pin_flow', 'actions', 'plan')


def quoted(value):
    """A YAML single-quoted scalar: the only escape inside is a doubled quote."""
    return "'" + str(value).replace("'", "''") + "'"


def resolve(base, path):
    """A flow path from the config, absolute, resolved against the config's folder."""
    candidate = pathlib.Path(path)
    return str(candidate if candidate.is_absolute() else (base / candidate).resolve())


def load(config_path):
    """The config, validated, with every flow path made absolute."""
    config = json.loads(pathlib.Path(config_path).read_text(encoding='utf-8'))
    missing = [key for key in REQUIRED if key not in config]
    if missing:
        raise ValueError(f'config is missing {", ".join(missing)}')
    if not re.match(r'^[a-z0-9_-]+$', config['persona']):
        raise ValueError('persona must be lowercase letters, digits, - or _')
    for key in ('clock', 'late_clock'):
        if not STAMP.match(config.setdefault(key, '07:30' if key == 'clock' else '00:30')):
            raise ValueError(f'{key} must be HH:MM')
    if not OFFSET.match(config.setdefault('offset', 'Z')):
        raise ValueError('offset must be Z or ±HH:MM')
    datetime.date.fromisoformat(config['first_date'])
    base = pathlib.Path(config_path).resolve().parent
    config['pin_flow'] = resolve(base, config['pin_flow'])
    for letter, action in config['actions'].items():
        if not LETTER.match(letter) or 'id' not in action:
            raise ValueError(f'action {letter!r} needs a single capital letter and an id')
        if 'then' in action:
            action['then'] = resolve(base, action['then'])
    config['extras'] = {int(day): [resolve(base, flow) for flow in flows]
                        for day, flows in config.get('extras', {}).items()}
    return config


def pin_steps(config, date, late):
    """The day's opening: pin the clock through the config's pin flow."""
    clock = config['late_clock'] if late else config['clock']
    stamp = f"{date.isoformat()}T{clock}:00{config['offset']}"
    return [
        '- runFlow:',
        f"    file: {quoted(config['pin_flow'])}",
        '    env:',
        f'      PERSONA_STAMP: {quoted(stamp)}',
        f'      PERSONA_DATE: {quoted(date.isoformat())}',
        f'      PERSONA_TIME: {quoted(clock)}',
    ]


def action_steps(action, index):
    """Scroll to the index-th match of the action's control, tap it, run its follow-up."""
    optional = ['    optional: true'] if action.get('optional') else []
    steps = [
        '- scrollUntilVisible:', '    element:', f"      id: {quoted(action['id'])}", f'      index: {index}',
        '    direction: DOWN', '    visibilityPercentage: 50', '    centerElement: true', '    timeout: 20000',
        *optional,
        '- tapOn:', f"    id: {quoted(action['id'])}", f'    index: {index}', *optional,
        '- waitForAnimationToEnd',
    ]
    if 'then' in action:
        steps.append(f"- runFlow: {quoted(action['then'])}")
    return steps


def day_flow(config, number, date, plan, extras):
    """The full flow text of one simulated day."""
    late = plan.startswith('@')
    shot = f"{config['persona']}-{number:02d}-{date.isoformat()}"
    lines = [f"appId: {quoted(config['appId'])}", '---', *pin_steps(config, date, late),
             '- waitForAnimationToEnd', f'- takeScreenshot: {quoted(shot + "-a")}']
    skipped = 0
    for letter in plan.lstrip('@'):
        if letter == '-':
            skipped += 1
            continue
        action = config['actions'].get(letter)
        if action is None:
            raise ValueError(f'day {number}: no action for {letter!r}')
        lines += action_steps(action, 0 if action.get('own_index') else skipped)
    lines.append(f'- takeScreenshot: {quoted(shot + "-b")}')
    lines += [f'- runFlow: {quoted(flow)}' for flow in extras]
    return '\n'.join(lines) + '\n'


def write_days(config, out_dir):
    """Write every day's flow; returns the written paths in day order."""
    out_dir = pathlib.Path(out_dir)
    first_day = int(config.get('first_day', 1))
    start = datetime.date.fromisoformat(config['first_date'])
    width = max(2, len(str(first_day + len(config['plan']) - 1)))
    # Every day is rendered before the folder is touched, so a plan that fails on any day
    # leaves the previous flows as they were.
    flows = []
    for offset, plan in enumerate(config['plan']):
        number = first_day + offset
        date = start + datetime.timedelta(days=offset)
        flow = day_flow(config, number, date, plan, config['extras'].get(number, []))
        flows.append((out_dir / f"{config['persona']}-{number:0{width}d}.yaml", flow))
    out_dir.mkdir(parents=True, exist_ok=True)
    # The runner runs every day file in the folder, so a day of an earlier plan left here
    # would run again: a shorter plan keeps its old tail, a change of name width keeps both.
    own = re.compile(re.escape(config['persona']) + r'-[0-9]+\.yaml')
    for stale in out_dir.iterdir():
        if own.fullmatch(stale.name):
            stale.unlink()
    for path, flow in flows:
        path.write_text(flow, encoding='utf-8')
    return [path for path, _ in flows]


def main(argv=None):
    """Generate the flows named by a config into an output folder."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    try:
        written = write_days(load(args[0]), args[1])
    except (ValueError, OSError, KeyError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(f'wrote {len(written)} day flows to {args[1]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
