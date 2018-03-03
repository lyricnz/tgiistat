#!/usr/bin/env python3

# Dumps modem statistics from a tgiinet1 modem.

# Thanks to Shannon Wynter for his https://github.com/freman/nbntest/ , some
# details were found there

# Matt Johnston (c) 2018 
# MIT license, see bottom of file.
# matt@ucc.asn.au

import argparse
import sys
import logging
import binascii
import re
import json

import requests
from bs4 import BeautifulSoup
import toml
import srp

D = logging.debug
L = logging.info
W = logging.warning
E = logging.error

def setup_logging(debug = False):
    level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(format='%(asctime)s %(message)s', 
            datefmt='%d/%m/%Y %I:%M:%S %p',
            level=level)
    #logging.getLogger("asyncio").setLevel(logging.DEBUG)

class Fetcher(object):
    def __init__(self, config):
        self.config = config
        self.top_url = 'http://%s' % self.config['address']
        self.session = None

    def connect(self):
        """ Authenticates with the modem. 
        Returns a session on success or throws an exception 
        """
        session = requests.Session()

        ### Fetch CSRF
        csrf_url = '%s/login.lp?action=getcsrf' % self.top_url
        csrf = session.get(csrf_url).text
        if len(csrf) != 64:
            D("csrf %s", csrf)
            raise Exception("Bad csrf response")
        D("csrf: %s" % csrf)

        ### Perform SRP
        srp_user = srp.User(self.config['username'], self.config['password'],
            hash_alg=srp.SHA256, ng_type=srp.NG_2048)
        # Bit of a bodge. Seems the router uses a custom k value? Thanks to nbntest
        srp._mod.BN_hex2bn(srp_user.k, b'05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300')

        I, A = srp_user.start_authentication()
        A = binascii.hexlify(A)
        D("A: %d %s" % (len(A), A))

        auth_url = '%s/authenticate' % self.top_url
        req_data = {
            'I': I, 
            'A': A, 
            'CSRFtoken': csrf
        }
        ### Send the first SRP request
        auth1 = session.post(auth_url, data=req_data)
        if auth1.status_code != 200:
            D(auth1.text)
            raise Exception("Error authenticating %d" % auth1.status_code)
        j = auth1.json()
        s, B = j['s'], j['B']
        D("s: %d %s" % (len(s), s))
        D("B: %d %s" % (len(B), B))
        s = binascii.unhexlify(s)
        B = binascii.unhexlify(B)

        M = srp_user.process_challenge(s, B)
        M = binascii.hexlify(M)
        D("M: %d %s" % (len(M), M))
        req_data = {
            'M': M, 
            'CSRFtoken': csrf
        }
        ### Send our reponse to the SRP challenge
        auth2 = session.post(auth_url, data=req_data)

        if auth2.status_code != 200:
            D(auth2.text)
            raise Exception("Didn't connect, error %d" % auth2.status_code)

        j = auth2.json()
        if 'error' in j:
            D(j)
            raise Exception("Authentication error. Wrong password? (%s)" % j['error'])

        return session

    def fetch(self):
        if not self.session:
            self.session = self.connect()

        modem_url = '%s/modals/broadband-bridge-modal.lp' % self.top_url
        r = self.session.get(modem_url)
        return r.text

def parse(html):
    res = {}
    soup = BeautifulSoup(html, 'html.parser')

    # use --parse to debug this with a file on disk
    def fetch_pair(title, unit):
        lr = soup.find_all(string=title)
        updown = lr[0].parent.parent.find_all(string=re.compile(unit))
        return (float(t.replace(unit,'').strip()) for t in updown)

    res['up_rate'], res['down_rate'] = fetch_pair("Line Rate", 'Mbps')
    res['up_power'], res['down_power'] = fetch_pair("Output Power", 'dBm')
    res['up_attenuation'], res['down_attenuation'] = fetch_pair("Line Attenuation", 'dB')
    res['up_noisemargin'], res['down_noisemargin'] = fetch_pair("Noise Margin", 'dB')

    return res

def print_plain(stats):
    print('\n'.join('%s %s' % (str(k), str(v)) for k, v in stats.items()))

def print_json(stats):
    print(json.dumps(stats, indent=4))

def main():
    parser = argparse.ArgumentParser(description=
"""Retrieves speed and other statistics from a Technicolor/iinet TGiiNet-1 modem.\n
Configure your details in tgiistat.toml\n 
"""
)
    parser.add_argument('--config', '-c', type=str, default='tgiistat.toml', help='Default is tgiistat.toml')
    parser.add_argument('--debug', '-d', action="store_true")
    parser.add_argument('--json', action="store_true", help="JSON output")
    parser.add_argument('--parse', type=argparse.FileType('r'), help="Parse html from a file", metavar='saved.html')

    args = parser.parse_args()

    setup_logging(args.debug)
    with open(args.config) as c:
        config_text = c.read()
    config = toml.loads(config_text)

    if args.parse:
        stats_page = args.parse.read()
    else:
        f = Fetcher(config)
        stats_page = f.fetch()
        D(stats_page)

    stats = parse(stats_page)

    if args.json:
        print_json(stats)
    else:
        print_plain(stats)
    

if __name__ == '__main__':
    main()

# Copyright (c) 2018 Matt Johnston
# All rights reserved.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
