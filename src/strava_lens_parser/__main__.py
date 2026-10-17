"""Validate an export without writing or printing personal records."""
import argparse
import collections
import json
from pathlib import Path
from . import iter_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--timezone', default='UTC')
    parser.add_argument('--summary-only', action='store_true')
    args = parser.parse_args()
    counts = collections.Counter()
    quarantined = 0
    try:
        for record in iter_export(args.archive, timezone=args.timezone,
                                  decode_streams=not args.summary_only):
            counts[record['kind']] += 1
            if record['kind'] == 'snapshot':
                quarantined = record['quarantined_streams']
    except Exception as error:
        parser.exit(1, 'Export rejected (' + type(error).__name__ + '); no records saved.\n')
    print(json.dumps({'status': 'valid_with_quarantined_streams' if quarantined else 'valid',
                      'counts': dict(counts), 'quarantined_streams': quarantined}))


if __name__ == '__main__':
    main()
