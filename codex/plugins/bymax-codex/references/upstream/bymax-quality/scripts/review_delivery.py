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


def cap(directory, pending=False):
    """Candidates this delivery may freeze: the budget, plus one more budget per extension.

    A pending extension counts before it is recorded, so the start it accompanies is
    validated against the figure it will have; it is written only if that start freezes.
    """
    ledger = load(directory) or {}
    return MAX_CANDIDATES * (1 + len(ledger.get('extensions', [])) + (1 if pending else 0))




def check_extension(directory, reason):
    """What an extension needs, checked before the start it accompanies does anything.

    The budget is an alarm about the corrections and the person watching it decides; the
    ledger is never deleted. The decision is written by reserve(), in the same write that
    freezes the candidate it authorises and after every validation, so a start refused for
    any reason has written nothing and the corrected retry carries the same flag.
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
    return ledger


def previous_head(directory):
    """The last candidate this delivery froze, or None: what a moved-aside campaign leaves."""
    ledger = load(directory)
    return ledger['heads'][-1] if ledger and ledger.get('heads') else None


def write(directory, ledger):
    """Replace the ledger atomically."""
    path = path_for(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(ledger, indent=2) + '\n')
    temporary.replace(path)


def scope_of(context):
    """The part of a campaign context the scope guards compare.

    `measured` is what the author ran against real data for the candidate in hand, so it
    changes as the candidate does — that is the field's whole purpose. Comparing it as scope
    made it write-once, and worse: a delivery whose ledger predates the field could not acquire
    it at all, because `context_contract` demanded the edit while the round guard and this
    ledger forbade it. Three guards closing a ring on a campaign that had done nothing wrong.

    Intent, acceptance, constraints, scope and checks are the contract a campaign is measured
    against. A reading taken under that contract is not the contract, and a guard that cannot
    tell them apart stops the author from recording what the reading found — which is the one
    thing nobody else can supply later.
    """
    try:
        data = json.loads(context)
    except (TypeError, ValueError):
        return context                      # not JSON: compare it exactly as before
    if not isinstance(data, dict):
        return context
    return json.dumps({k: v for k, v in data.items() if k != 'measured'}, sort_keys=True)


def reserve(directory, head, base, context, old=None, extension=''):
    """Count a frozen candidate once, retaining the budget across cleared campaigns.

    The caller holds the campaign lock. A reservation preceding a crashed state write
    is reusable only for that same head, so a crash neither spends a second slot nor
    creates an uncounted candidate. A new feature uses a new branch/delivery. A decision
    to continue past the budget is written here too, in the same write as the head it
    authorises, so the ledger changes once and only when a candidate freezes.
    """
    ledger = load(directory) or dict(base=base, context=context, heads=[], used=0)
    if ledger['base'] != base or scope_of(ledger['context']) != scope_of(context):
        raise ValueError('Delivery scope changed. Keep its base/context for PR corrections; new work needs a new branch.')
    if head not in ledger['heads']:
        used = max(ledger['used'], (old or {}).get('round', 0))
        if old and old['head'] == head:
            used = max(0, used - 1)
        if extension:
            check_extension(directory, extension)
            ledger.setdefault('extensions', []).append(dict(at_used=ledger['used'], reason=extension.strip()))
        limit = MAX_CANDIDATES * (1 + len(ledger.get('extensions', [])))
        if used >= limit:
            raise ValueError(f'Delivery budget exhausted ({limit} candidates across pushes). This is the '
                             'alarm that the corrections keep producing the next finding. Preserve the '
                             'evidence; never reset the ledger. If a human decides to continue anyway, record '
                             'it with --extend-delivery "<who authorised it, and why>"; both reviewers are told.')
        ledger['heads'].append(head)
        ledger['used'] = used + 1
        # The scope is unchanged by the check above, so what differs is the measurement, and the
        # ledger carries the current one: written here, in the same write as the head it belongs
        # to, so the ledger still changes once and only when a candidate freezes.
        ledger['context'] = context
        write(directory, ledger)
    return dict(autonomous=True, max_rounds=MAX_CANDIDATES * (1 + len(ledger.get('extensions', []))),
                delivery_used=ledger['used'], delivery_extensions=ledger.get('extensions', []))
