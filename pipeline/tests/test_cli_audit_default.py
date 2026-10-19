"""The CLI audits with the bounded sample by default; --no-audit-bound restores the Bernoulli audit."""

import argparse

import acts.__main__ as cli


def _run_args(argv):
    seen = {}

    def capture(args: argparse.Namespace) -> int:
        seen["args"] = args
        return 0

    original = cli.cmd_run
    cli.cmd_run = capture
    try:
        # set_defaults(func=cmd_run) is bound when main() builds the parser.
        cli.main(["run", "--strategy", "reference"] + argv + ["--", "true"])
    finally:
        cli.cmd_run = original
    return seen["args"]


def test_bounded_audit_is_the_default():
    args = _run_args([])
    assert args.audit_bound is True
    assert args.first_use == 0


def test_no_audit_bound_restores_bernoulli():
    args = _run_args(["--no-audit-bound"])
    assert args.audit_bound is False
