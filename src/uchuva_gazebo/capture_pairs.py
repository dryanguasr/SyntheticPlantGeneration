"""Select original synchronized exposures without inventing frames."""


def select_pairs(index, rate_hz=5):
    if rate_hz is not None and rate_hz <= 0:
        raise ValueError('Capture selection rate must be positive or None')
    stamps = sorted(set(index['rgb']) & set(index['mask']), key=int)
    chosen = {}
    for stamp in stamps:
        period = 1e9 / rate_hz if rate_hz is not None else 1
        bucket = round(int(stamp) / period) if rate_hz is not None else int(stamp)
        if bucket not in chosen or abs(int(stamp)-bucket*period) < abs(int(chosen[bucket])-bucket*period):
            chosen[bucket] = stamp
    pairs = [dict(stamp_ns=int(s), rgb=index['rgb'][s], mask=index['mask'][s]) for s in chosen.values()]
    missing = [dict(stamp_ns=int(s), missing='mask' if s in index['rgb'] else 'rgb')
               for s in sorted(set(index['rgb']) ^ set(index['mask']), key=int)]
    return pairs, missing
