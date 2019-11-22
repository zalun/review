#!/usr/bin/env python2.7
# coding=utf-8
import sys
from time import sleep
import json
import subprocess
import functools

# import urllib.request as request
import urllib2 as request

# import urllib.parse as urlparse
from urllib2 import quote
import signal
import urlparse
import threading
import contextlib


HAS_ANSI = False


def to_llist(revisions):
    llist = {}
    for i, revision in enumerate(revisions):
        child = revisions[i + 1] if i + 1 < len(revisions) else None
        llist[revision] = child
    return llist


def walk_llist(llist, allow_multiple_heads=False):
    referenced_children = [r for r in llist.values() if r]

    # Find head
    node = None
    for n in sorted(llist.keys()):
        if n not in referenced_children:
            if node:
                if not allow_multiple_heads:
                    raise Exception("Multiple heads found in: %s" % llist)
                break
            node = n
    if not node:
        raise Exception("Failed to find head in: %s" % llist)

    # Walk list, checking for loops
    nodes = []
    while node:
        nodes.append(node)

        child = llist[node]
        if child and child in nodes:
            raise Exception("Dependency loop in: %s" % llist)

        node = child

    return nodes


def stack_transactions(remote_phids, local_phids):
    remote_list = to_llist(remote_phids)
    local_list = to_llist(local_phids)

    print("%s --> %s" % (remote_phids, local_phids))
    transactions = {}
    for revision in remote_phids + local_phids:
        transactions[revision] = []

    # remote no longer in stack
    for revision in [r for r in remote_phids if r not in local_phids]:
        # transactions.append("%s: set-child %s" % (revision, None))
        transactions[revision].append(("children.set", None))
        remote_list[revision] = None
        walk_llist(remote_list, allow_multiple_heads=True)

    # new revisions
    for revision in [r for r in local_phids if r not in remote_phids]:
        child = local_list[revision]
        # transactions.append("%s: set-child %s" % (revision, child))
        transactions[revision].append(("children.set", child))
        remote_list[revision] = child
        walk_llist(remote_list, allow_multiple_heads=True)

    for revision in [r for r in remote_phids if r in local_phids]:
        if local_list[revision] != remote_list[revision]:
            # transactions.append("%s: set-child %s" % (revision, local_list[revision]))
            transactions[revision].append(("children.set", local_list[revision]))
            remote_list[revision] = local_list[revision]
            walk_llist(remote_list, allow_multiple_heads=True)

    # for revision in set(remote_revisions) - set(local_revisions):
    for revision in [r for r in remote_phids if r not in local_phids]:
        # transactions.append("%s: abandon" % revision)
        transactions[revision].append(("abandon", True))
        del remote_list[revision]
        walk_llist(remote_list, allow_multiple_heads=True)

    assert ":".join(walk_llist(remote_list)) == ":".join(walk_llist(local_list))

    conduit_transactions = {}
    for revision, transaction_list in transactions.items():
        if not transaction_list:
            continue
        conduit_transactions.setdefault(revision, [])
        for transaction in transaction_list:
            k, v = transaction
            if k == "children.set" and v:
                v = v
            conduit_transactions[revision].append({"type": k, "value": v})

    return json.dumps(conduit_transactions, indent=2, sort_keys=True)


def test():
    print("%s\n" % stack_transactions(["A", "B", "C"], ["A"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["B"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["C"]))

    print("%s\n" % stack_transactions(["A", "B", "C"], ["B", "C"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["A", "C"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["A", "B"]))

    print("%s\n" % stack_transactions(["A", "B", "C"], ["A", "B", "C"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["A", "C", "B"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["B", "A", "C"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["B", "C", "A"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["C", "A", "B"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["C", "B", "A"]))

    print("%s\n" % stack_transactions(["A", "B", "C"], ["D", "A", "B", "C"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["A", "D", "B", "C"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["A", "B", "D", "C"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["A", "B", "C", "D"]))

    print("%s\n" % stack_transactions(["A", "B", "C"], ["D", "B", "C", "A"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["B", "D", "C", "A"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["B", "C", "D", "A"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["B", "C", "A", "D"]))

    print("%s\n" % stack_transactions(["A", "B", "C"], ["D", "C", "A", "B"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["C", "D", "A", "B"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["C", "A", "D", "B"]))
    print("%s\n" % stack_transactions(["A", "B", "C"], ["C", "A", "B", "D"]))


def __conduit(method, **kwargs):
    args = json.dumps(dict(**kwargs), separators=(",", ":"))
    print("%s %s" % (method, args))
    p = subprocess.run(
        ["arc", "call-conduit", method],
        check=True,
        input=args,
        cwd="/Users/byron/dev/mozilla-central",
        encoding="utf8",
        capture_output=True,
    )
    res = json.loads(p.stdout)
    if res["error"]:
        raise Exception(res["errorMessage"])
    return res["response"]


def conduit(method, **kwargs):
    api_params = []

    def _append_api_param(path, param):
        if type(param) == list:
            for (index, v) in enumerate(param):
                _append_api_param("%s[%s]" % (path, index), v)

        elif type(param) == dict:
            for (k, v) in param.items():
                _append_api_param("%s[%s]" % (path, k), v)

        else:
            api_params.append((path, str(param)))

    kwargs.setdefault("api.token", "cli-XXX")
    for (key, value) in kwargs.items():
        _append_api_param(key, value)

    url = urlparse.urljoin("https://phabricator.services.mozilla.com/api/", method)
    data = "&".join(["%s=%s" % (k, quote(v)) for (k, v) in api_params])

    # print("%s\n  %s" % (url, [p for p in api_params if p[0] != "api.token"]))

    req = request.Request(url, data=data.encode("utf8"))

    with contextlib.closing(request.urlopen(req)) as r:
        res = r.read()

    res = json.loads(res)
    if res["error_code"] and res["error_info"]:
        raise Exception(res["error_info"])
    return res["result"]


# @functools.lru_cache()
def id_to_phid(revision):
    if revision.startswith("PHID-"):
        return revision
    if revision.startswith("D"):
        revision = revision[1:]

    res = conduit("differential.revision.search", constraints={"ids": [int(revision)]})
    if not res["data"]:
        raise Exception("bad revision id: D%s" % revision)
    return res["data"][0]["phid"]


# @functools.lru_cache()
def phid_to_id(phid):
    if phid.startswith("D"):
        return phid[1:]

    res = conduit("differential.revision.search", constraints={"phids": [phid]})
    if not res["data"]:
        raise Exception("bad revision phid: %s" % phid)
    return res["data"][0]["id"]


def get_stack(phid):
    phids = set()
    new_phids = {phid}
    stack = {}

    while new_phids:
        phids.update(new_phids)

        edges = conduit(
            "edge.search",
            sourcePHIDs=list(new_phids),
            types=["revision.parent", "revision.child"],
            limit=10000,
        )["data"]

        new_phids = set()
        for edge in edges:
            new_phids.add(edge["sourcePHID"])
            new_phids.add(edge["destinationPHID"])

            if edge["edgeType"] == "revision.child":
                assert edge["sourcePHID"] not in stack
                stack[edge["sourcePHID"]] = edge["destinationPHID"]

        new_phids = new_phids - phids

    for child in list(stack.values()):
        stack.setdefault(child)

    return stack


class PhabricatorStackThread(threading.Thread):
    def __init__(self, revision):
        super(PhabricatorStackThread, self).__init__()
        self._revision = revision
        self.daemon = True
        self.stack = None

    def run(self):
        self.stack = get_stack(id_to_phid(self._revision))


# noinspection PyUnusedLocal
class SigIntHandler(object):
    def __init__(self):
        self.triggered = False

    def signal_handler(self, sig, frame):
        self.triggered = True


sig_int = SigIntHandler()
signal.signal(signal.SIGINT, sig_int.signal_handler)


class Spinner(threading.Thread):
    def __init__(self):
        super(Spinner, self).__init__()
        self.daemon = True
        self.running = False

    def run(self):
        self.running = True
        spinner = ["-", "\\", "|", "/"]
        spin = 0
        sys.stdout.write(" ")
        try:
            while self.running:
                sys.stdout.write(chr(8) + spinner[spin])
                sys.stdout.flush()
                spin = (spin + 1) % len(spinner)
                sleep(0.2)
        finally:
            sys.stdout.write(chr(8) + " ")
            sys.stdout.flush()


@contextlib.contextmanager
def wait_message(message):
    sys.stdout.write("\033[90m%s " % message if HAS_ANSI else "%s " % message)
    sys.stdout.flush()
    spinner = Spinner()
    spinner.start()
    try:
        yield
    finally:
        spinner.running = False
        spinner.join()
        sys.stdout.write("\033[0m\r\033[K" if HAS_ANSI else "\n")
        if sig_int.triggered:
            print("Cancelled")
            sys.exit(3)


def main():
    test()
    exit()
    stack_thread = PhabricatorStackThread("D27984")
    stack_thread.start()

    with wait_message("Examining existing stack on Phabricator"):
        stack_thread.join()
    stack_llist = stack_thread.stack

    # stack_llist = get_stack(id_to_phid("D27984"))
    # stack_llist = get_stack("PHID-DREV-bxz34yuy52y3lktj7v33")
    print(stack_llist)
    stack = walk_llist(stack_llist)
    print(stack)
    with wait_message("Resolving PHIDs"):
        stack_revs = ["D%s" % phid_to_id(node) for node in stack]
    print(stack_revs)
    print("%s\n" % stack_transactions(stack, ["PHID-DREV-bxz34yuy52y3lktj7v33"]))


main()
