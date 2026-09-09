#!/usr/bin/env python3
"""Use the domains skill's SOPS credential for a single Cloudflare DNS request."""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('method', choices=['GET', 'POST', 'PATCH'])
    parser.add_argument('path', help='Relative API path, for example /zones?name=0xc1.space')
    parser.add_argument('--body', type=Path, help='JSON request body file for POST/PATCH')
    args = parser.parse_args()
    url = urlsplit(args.path)
    zone = r'/zones(?:/[a-f0-9]{32}(?:/dns_records(?:/[a-f0-9]{32})?)?)?'
    if (url.scheme or url.netloc or url.fragment or not args.path.startswith('/')
            or not re.fullmatch(r'(?:/user/tokens/verify|' + zone + ')', url.path)):
        parser.error('Only relative Cloudflare zone, DNS, or token verification paths are allowed')
    if args.method != 'GET':
        suffix = r'/[a-f0-9]{32}' if args.method == 'PATCH' else ''
        if not re.fullmatch(r'/zones/[a-f0-9]{32}/dns_records' + suffix, url.path):
            parser.error('Writes must target a DNS collection (POST) or record (PATCH)')
    if (args.method == 'GET') == bool(args.body):
        parser.error('GET takes no body; POST/PATCH require --body')
    body = None
    if args.body:
        try:
            payload = json.loads(args.body.read_text())
            if not isinstance(payload, dict):
                raise ValueError()
            body = json.dumps(payload).encode()
        except (OSError, ValueError):
            parser.error('Body must be a readable JSON object file')

    secret_file = Path(__file__).resolve().parents[1] / 'references/secrets.enc.yaml'
    try:
        result = subprocess.run(
            ['sops', 'decrypt', '--output-type', 'json', str(secret_file)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30,
        )
        token = json.loads(result.stdout)['cloudflare']['api_token']
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', token):
            raise ValueError()
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        sys.exit('SOPS credential unavailable; check SOPS and the matching SSH private key on Charlie')

    request = urllib.request.Request(
        'https://api.cloudflare.com/client/v4' + args.path,
        data=body, method=args.method,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit('Cloudflare HTTP ' + str(error.code) + '; request failed, no success assumed')
    except (urllib.error.URLError, OSError, ValueError):
        sys.exit('Cloudflare request failed; verify current DNS state before retrying a write')
    if not isinstance(data, dict) or not data.get('success'):
        sys.exit('Cloudflare returned an unsuccessful API result')
    print(json.dumps(data, ensure_ascii=False, indent=2).replace(token, '[REDACTED]'))


if __name__ == '__main__':
    main()
