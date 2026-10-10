#!/usr/bin/env python3
"""One ProcessCache route: linux/amd64 under Docker emulation.

Pre-registered in pipeline/docs/BASELINES_PROTOCOL.md, addendum
"ProcessCache linux/amd64 emulation probe". Does not patch
regs.rs. The ptrace probe is the uniform smoke's abi.c. A failed
probe stops the run; the behavioral sequence runs only if the
probe succeeds.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import baseline_docker_uniform as uniform  # noqa: E402

AMD64_DIGEST = "sha256:08ea48a03a3e78ebc7cd526e6a275053223aadd88bfc09cc49b06d5281525fde"
IMAGE = f"ubuntu:22.04@{AMD64_DIGEST}"
SEQUENCE_IMAGE = "acts-processcache-amd64:local"
DOCKERFILE = ROOT / "docker" / "Dockerfile.baselines_processcache_amd64"
PC_COMMIT = "a89d13214d8a0a9527ad4400a0a7284158d952a1"


def probe_script() -> str:
    source = uniform.ABI_C
    return f"""set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends gcc libc6-dev ca-certificates
cat > /tmp/abi.c << 'END_ABI'
{source}END_ABI
gcc -O2 -Wall -o /tmp/abi /tmp/abi.c
echo "ACTS_UNAME $(uname -a)"
/tmp/abi
echo "ACTS_PROBE_EXIT $?"
"""


def docker_probe_argv(script: str) -> list[str]:
    return [
        "docker", "run", "--rm",
        "--platform", "linux/amd64",
        "--cap-add", "SYS_PTRACE",
        IMAGE,
        "bash", "-lc", script,
    ]


def run_probe() -> dict:
    script = probe_script()
    proc = subprocess.run(
        docker_probe_argv(script),
        check=False,
        text=True,
        capture_output=True,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    probe = uniform._parse_probe(text)
    return {
        "docker_exit": proc.returncode,
        "probe": probe,
        "log": text[-8000:],
        "succeeded": bool(probe.get("succeeded")) and proc.returncode == 0,
    }


def result_payload(probe: dict) -> dict:
    uname = platform.uname()
    return {
        "label": "MEASURED",
        "decides": "whether ProcessCache's ptrace request works in a linux/amd64 container under emulation",
        "protocol": "pipeline/docs/BASELINES_PROTOCOL.md",
        "addendum": "2026-10-10 ProcessCache linux/amd64 emulation probe",
        "image": IMAGE,
        "platform": "linux/amd64",
        "emulation": "Docker --platform linux/amd64 on this arm64 host",
        "capabilities": {
            "privileged": False,
            "cap_add": "SYS_PTRACE",
            "seccomp": "default Docker profile; not seccomp=unconfined",
        },
        "processcache_commit": PC_COMMIT,
        "regs_rs_patched": False,
        "behavioral_sequence": "not run" if not probe["succeeded"] else "pending",
        "probe": probe["probe"],
        "docker_exit": probe["docker_exit"],
        "probe_succeeded": probe["succeeded"],
        "log_tail": probe["log"][-4000:],
        "provenance": {
            "host": platform.node(),
            "platform": platform.platform(),
            "uname": f"{uname.system} {uname.release} {uname.machine}",
            "python": platform.python_version(),
        },
    }


def build_sequence_image() -> int:
    proc = subprocess.run(
        [
            "docker", "build",
            "--platform", "linux/amd64",
            "-f", str(DOCKERFILE),
            "-t", SEQUENCE_IMAGE,
            str(DOCKERFILE.parent),
        ],
        check=False,
    )
    return proc.returncode


def sequence_docker_argv(work: Path, script: str) -> list[str]:
    return [
        "docker", "run", "--rm",
        "--platform", "linux/amd64",
        "--cap-add", "SYS_PTRACE",
        "-v", f"{work}:/work",
        "-w", "/data",
        SEQUENCE_IMAGE,
        "bash", "-lc", script,
    ]


def run_sequence(data_root: Path, work: Path) -> dict:
    """Uniform ProcessCache sequence inside the amd64 image.

    Same argv and subset as baseline_docker_uniform.sequence_script.
    Called only after the ptrace probe succeeded.
    """
    uniform.prepare_work(work, data_root)
    script = uniform.sequence_script("processcache")
    argv = sequence_docker_argv(work, script)
    proc = subprocess.run(argv, check=False, text=True, capture_output=True)
    text = (proc.stdout or "") + (proc.stderr or "")
    (work / "out").mkdir(parents=True, exist_ok=True)
    (work / "out" / "docker.log").write_text(text)
    scored = uniform.score_column("processcache", work, proc.stdout or "", proc.returncode)
    return {"docker_exit": proc.returncode, "log_tail": text[-4000:], **scored}


def main() -> None:
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results" / "baseline_processcache_amd64.json",
    )
    parser.add_argument(
        "--sequence",
        action="store_true",
        help="run the uniform behavioral sequence; requires a recorded successful probe",
    )
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/acts-processcache-amd64"))
    args = parser.parse_args()
    if args.sequence:
        if not args.out.is_file():
            raise SystemExit("probe result is missing; run the probe first")
        payload = json.loads(args.out.read_text())
        if not payload.get("probe_succeeded"):
            raise SystemExit("probe did not succeed; sequence is not run")
        if args.data_root is None:
            raise SystemExit("--data-root is required for the sequence")
        sequence = run_sequence(args.data_root, args.work)
        payload["sequence_image"] = SEQUENCE_IMAGE
        payload["sequence_platform"] = "linux/amd64"
        payload["regs_rs_patched"] = False
        payload["behavioral_sequence"] = sequence
        payload["sequence_provenance"] = uniform.host_provenance()
        args.out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {args.out}")
        print("docker_exit", sequence["docker_exit"], "binary_missing", sequence["binary_missing"])
        return
    probe = run_probe()
    payload = result_payload(probe)
    if probe["succeeded"]:
        payload["behavioral_sequence"] = "pending"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.out}")
    print("probe_succeeded", payload["probe_succeeded"], "probe", payload["probe"])


if __name__ == "__main__":
    main()
