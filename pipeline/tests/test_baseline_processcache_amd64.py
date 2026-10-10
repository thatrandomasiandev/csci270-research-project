"""The amd64 ProcessCache route is emulation plus the existing ptrace probe."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE / "scripts"))

import baseline_docker_uniform as uniform  # noqa: E402
import baseline_processcache_amd64 as amd  # noqa: E402


class ProcessCacheAmd64GuardTests(unittest.TestCase):
    def test_probe_uses_the_uniform_abi_and_amd64_digest(self) -> None:
        script = amd.probe_script()
        argv = amd.docker_probe_argv(script)
        self.assertIn(uniform.ABI_C, script)
        self.assertIn("--platform", argv)
        self.assertIn("linux/amd64", argv)
        self.assertIn("--cap-add", argv)
        self.assertIn("SYS_PTRACE", argv)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("seccomp=unconfined", argv)
        self.assertIn(amd.AMD64_DIGEST, amd.IMAGE)
        self.assertNotIn("gs_base", script)
        self.assertNotIn("regs.rs", script)

    def test_failed_probe_does_not_claim_a_behavioral_run(self) -> None:
        payload = amd.result_payload({
            "docker_exit": 1,
            "probe": {"rc": None, "errno": None, "succeeded": False},
            "log": "exec format error",
            "succeeded": False,
        })
        self.assertFalse(payload["probe_succeeded"])
        self.assertEqual(payload["behavioral_sequence"], "not run")
        self.assertFalse(payload["regs_rs_patched"])
        self.assertEqual(payload["processcache_commit"], amd.PC_COMMIT)

    def test_sequence_uses_emulated_amd64_without_privilege(self) -> None:
        argv = amd.sequence_docker_argv(Path("/tmp/pc"), "true")
        self.assertIn("--platform", argv)
        self.assertIn("linux/amd64", argv)
        self.assertIn("--cap-add", argv)
        self.assertIn("SYS_PTRACE", argv)
        self.assertNotIn("--privileged", argv)
        self.assertEqual(argv[argv.index(amd.SEQUENCE_IMAGE) + 1], "bash")
        self.assertIn("libseccomp-dev", (PIPE / "docker" / "Dockerfile.baselines_processcache_amd64").read_text())

    def test_amd64_dockerfile_does_not_patch_regs(self) -> None:
        text = (PIPE / "docker" / "Dockerfile.baselines_processcache_amd64").read_text()
        self.assertIn(amd.AMD64_DIGEST, text)
        self.assertIn(amd.PC_COMMIT, text)
        self.assertNotIn("sed -i", text)
        self.assertNotIn("gs_base", text)
        self.assertIn("DONT_HASH_FILES stays false", text)


if __name__ == "__main__":
    unittest.main()
