"""Lab simulator tests: kinematics vs the controller, and a real Studio project.

The simulator is browser JavaScript; these tests run it under Node (skipped
when Node is missing). No robot, camera or browser is involved.
"""

import json
from pathlib import Path
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

from labdeck.server import static_asset

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).parent / "data"
NS = "{https://developers.google.com/blockly/xml}"
NODE = shutil.which("node")


def tree(block):
    """Mirror of lab.js treeFromDom: Blockly XML block → plain dict."""
    if block is None:
        return None
    node = {
        "type": block.get("type"),
        "id": block.get("id"),
        "fields": {},
        "fieldOrder": [],
        "values": {},
        "statements": {},
    }
    for child in block:
        tag = child.tag.replace(NS, "")
        if tag == "field":
            node["fields"][child.get("name")] = child.text or ""
            node["fieldOrder"].append(child.get("name"))
        elif tag in ("value", "statement"):
            inner = child.find(NS + "block") or child.find(NS + "shadow")
            if inner is None:
                inner = child.find(NS + "shadow")
            if child.get("name", "").startswith("btn_"):
                continue  # Studio's editor-only buttons
            (node["values"] if tag == "value" else node["statements"])[
                child.get("name")
            ] = tree(inner)
        elif tag == "next":
            node["next"] = tree(child.find(NS + "block"))
        elif tag == "mutation":
            node["mutationName"] = child.get("name")
    return node


def run_node(script):
    result = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, cwd=ROOT, timeout=60
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


@unittest.skipUnless(NODE, "Node.js not installed")
class LabSimulatorTests(unittest.TestCase):
    def test_nominal_fk_is_close_to_the_controller_and_calibrated_is_exact(self):
        out = run_node(
            """
            const K = require('./assets/lab/kinematics.js');
            const ref = require('./tests/data/lab_fk_reference.json');
            const worst = () => Math.max(...ref.cases.map(c => {
              const p = K.fk(c.joints, ref.tcp_offset);
              return Math.hypot(p[0]-c.pose[0], p[1]-c.pose[1], p[2]-c.pose[2]);
            }));
            const nominal = worst();
            let calibrated = null;
            try { K.setGeometry(require('./local/lab-kinematics.json').joints); calibrated = worst(); } catch (e) {}
            console.log(JSON.stringify({nominal, calibrated}));
            """
        )
        # Published geometry is nominal; per-arm calibration makes it exact.
        self.assertLess(out["nominal"], 12)
        if out["calibrated"] is not None:
            self.assertLess(out["calibrated"], 1.0)

    def test_ik_round_trip(self):
        out = run_node(
            """
            const K = require('./assets/lab/kinematics.js');
            const q = [3.46, 20.3, 64.39, -179.48, -42.24, 180.84];
            const r = K.ik(K.fk(q), [0, 10, 50, -170, -30, 170]);
            console.log(JSON.stringify({ok: r.ok, err: r.posErr, joints: r.joints}));
            """
        )
        self.assertTrue(out["ok"])
        for a, b in zip(out["joints"], [3.46, 20.3, 64.39, -179.48, -42.24, 180.84]):
            self.assertAlmostEqual(a, b, delta=0.05)

    def test_real_studio_vacuum_project_compiles_to_the_expected_timeline(self):
        root = ET.parse(DATA / "studio_vacuum_project.xml").getroot()
        stacks = [tree(b) for b in root.findall(NS + "block")]
        out = run_node(
            f"""
            const P = require('./assets/lab/program.js');
            const r = P.compile({json.dumps(stacks)}, {{startJoints: [0,0,0,0,0,0]}});
            const kinds = {{}};
            for (const s of r.segments) kinds[s.kind] = (kinds[s.kind] || 0) + 1;
            console.log(JSON.stringify({{kinds, duration: r.duration,
              findings: r.findings, end: r.endJoints}}));
            """
        )
        # repeat 5 × (8 joint moves, 6 suction switches, 2 waits)
        self.assertEqual(out["kinds"], {"joint": 40, "suction": 30, "wait": 10})
        self.assertGreater(out["duration"], 5 * 10)  # two waits of 6 s and 4 s per loop
        for a, b in zip(out["end"], [-31.2, 21.6, 33.1, 110.9, -12.2, -74.5]):
            self.assertAlmostEqual(a, b, places=6)
        self.assertFalse([f for f in out["findings"] if f["level"] == "error"])

    def test_findings_point_at_the_block(self):
        stacks = [
            {
                "type": "move_cartesian",
                "id": "far",
                "fields": {
                    "x": "900",
                    "y": "0",
                    "z": "200",
                    "roll": "180",
                    "pitch": "0",
                    "yaw": "0",
                    "r": "0",
                    "wait": "TRUE",
                },
                "fieldOrder": ["x", "y", "z", "roll", "pitch", "yaw", "r", "wait"],
                "values": {},
                "statements": {},
            },
        ]
        out = run_node(
            f"""
            const P = require('./assets/lab/program.js');
            const r = P.compile({json.dumps(stacks)}, {{startJoints: [0, 10, 30, 0, 20, 0]}});
            console.log(JSON.stringify(r.findings));
            """
        )
        self.assertTrue(
            any(f["blockId"] == "far" and "Unreachable" in f["message"] for f in out)
        )


class StaticAssetTests(unittest.TestCase):
    def test_serves_lab_files_but_never_outside_assets(self):
        self.assertIsNotNone(static_asset("/assets/lab/kinematics.js"))
        for path in [
            "/assets/../local/lab.toml",
            "/assets/vendor/../../local/lab.toml",
            "/assets/index.html",
            "/assets/lab",
        ]:
            self.assertIsNone(static_asset(path), path)


if __name__ == "__main__":
    unittest.main()
