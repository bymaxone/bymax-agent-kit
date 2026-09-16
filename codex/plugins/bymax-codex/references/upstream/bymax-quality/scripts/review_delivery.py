"""Delivery policy layer: persist the autonomous candidate budget outside campaign archives."""
import json

MAX_CANDIDATES = 6


def path_for(directory):
    """Keep the branch delivery ledger independent of campaign directory renames."""
    return directory.parent / 'deliveries' / (directory.name + '.json')


def load(directory):
    """Read an existing delivery without creating or resetting it."""
    path = path_for(directory)
    return json.loads(path.read_text()) if path.exists() else None


def active(directory, requested=False):
    """Once enrolled, every start on this branch shares the delivery budget."""
    return requested or path_for(directory).exists()


def cap(directory):
    """Candidates this delivery may freeze: the budget, plus one more budget per extension."""
    ledger = load(directory) or {}
    return MAX_CANDIDATES * (1 + len(ledger.get('extensions', [])))


def extend(directory, reason):
    """Record who decided to continue past a spent budget, and why; both reviewers read it.

    The budget is an alarm about the corrections and the person watching it decides; the
    ledger is never deleted. An extension is recorded only when the budget is actually
    spent, so a flag passed early or on a start that is then refused cannot pre-buy a
    budget, and only with a reason that says something.
    """
    ledger = load(directory)
    if ledger is None:
        raise ValueError('No delivery to extend on this branch: enroll with --autonomous first.')
    if not reason.strip():
        raise ValueError('--extend-delivery needs a reason: who decided to continue, and why.')
    limit = MAX_CANDIDATES * (1 + len(ledger.get('extensions', [])))
    if ledger['used'] < limit:
        raise ValueError(f"The delivery budget is not spent ({ledger['used']} of {limit} candidates); "
                         'there is nothing to extend yet.')
    ledger.setdefault('extensions', []).append(dict(at_used=ledger['used'], reason=reason.strip()))
    write(directory, ledger)


def previous_head(directory):
    """The last candidate this delivery froze, or None: what a moved-aside campaign loses."""
    ledger = load(directory)
    return ledger['heads'][-1] if ledger and ledger.get('heads') else None


def write(directory, ledger):
    """Replace the ledger atomically."""
    path = path_for(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(ledger, indent=2) + '\n')
    temporary.replace(path)


def reserve(directory, head, base, context, old=None):
    """Count a frozen candidate once, retaining the budget across cleared campaigns.

    The caller holds the campaign lock. A reservation preceding a crashed state write
    is reusable only for that same head, so a crash neither spends a second slot nor
    creates an uncounted candidate. A new feature uses a new branch/delivery.
    """
    ledger = load(directory) or dict(base=base, context=context, heads=[], used=0)
    if ledger['base'] != base or ledger['context'] != context:
        raise ValueError('Delivery scope changed. Keep its base/context for PR corrections; new work needs a new branch.')
    if head not in ledger['heads']:
        used = max(ledger['used'], (old or {}).get('round', 0))
        if old and old['head'] == head:
            used = max(0, used - 1)
        limit = MAX_CANDIDATES * (1 + len(ledger.get('extensions', [])))
        if used >= limit:
            raise ValueError(f'Delivery budget exhausted ({limit} candidates across pushes). This is the '
                             'alarm that the corrections keep producing the next finding. Preserve the '
                             'evidence; never reset the ledger. If a human decides to continue anyway, record '
                             'it with --extend-delivery "<who authorised it, and why>"; both reviewers are told.')
        ledger['heads'].append(head)
        ledger['used'] = used + 1
        write(directory, ledger)
    return dict(autonomous=True, max_rounds=MAX_CANDIDATES * (1 + len(ledger.get('extensions', []))),
                delivery_used=ledger['used'], delivery_extensions=ledger.get('extensions', []))
