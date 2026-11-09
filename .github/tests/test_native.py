"""Execute live workflow shell blocks with a closed PATH and native-tool stubs."""

import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/release.yml").read_text()
SPEC = importlib.util.spec_from_file_location(
    "native_source_version", ROOT / ".github/scripts/source_version.py"
)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def step(name):
    """Test the actual run block, never a parallel implementation."""
    matches = re.findall(
        rf"^      - name: {re.escape(name)}\n"
        r"(?:(?!      - ).*\n)*?        run: \|\n"
        r"((?:          .*(?:\n|$)|[ \t]*\n)+)",
        WORKFLOW, re.MULTILINE,
    )
    if len(matches) != 1:
        raise AssertionError(f"Expected one shell block for {name!r}")
    return textwrap.dedent(matches[0])


STUB = r'''
import json
import os
from pathlib import Path
import plistlib
import re
import sys

tool = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path.cwd()
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([tool, *args]) + "\n")
bundle = root / os.environ["BUNDLE_PATH"]
contents = bundle / "Contents"
mode = os.environ.get("BUILD_MODE", "complete")

if tool == "xcodebuild":
    for path in (
        contents / "MacOS/Kana", contents / "Info.plist",
        contents / "Resources/English.lproj/InfoPlist.strings",
        contents / "_CodeSignature", bundle.parent / "Default",
        bundle.parent / "Kana.build",
    ):
        assert not path.exists(), "stale output survived: " + str(path)
    if mode == "failure":
        sys.exit(70)
    if mode != "missing-binary":
        (contents / "MacOS").mkdir(parents=True, exist_ok=True)
        (contents / "MacOS/Kana").write_bytes(b"rebuilt-universal")
    if mode != "missing-plist":
        data = plistlib.loads((root / "Info.plist").read_bytes())
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            if key in data:
                data[key] = re.sub(
                    r"\$\([^)]+\)|\$\{[^}]+\}", os.environ["SOURCE_VERSION"], data[key]
                )
        if mode == "stale-plist":
            data["CFBundleShortVersionString"] = os.environ["STALE_VERSION"]
        if mode == "stale-build-version":
            data["CFBundleVersion"] = os.environ["STALE_VERSION"]
        (contents / "Info.plist").write_bytes(plistlib.dumps(data))
    if mode != "missing-localized":
        target = contents / "Resources/English.lproj/InfoPlist.strings"
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (root / "English.lproj/InfoPlist.strings").read_bytes()
        if mode == "stale-localized":
            data = data.replace(
                os.environ["SOURCE_VERSION"].encode(), os.environ["STALE_VERSION"].encode()
            )
        target.write_bytes(data)
elif tool == "lipo":
    assert len(args) == 2 and args[0] in ("-info", "-archs"), args
    assert Path(args[1]).is_file(), args
    architectures = os.environ.get(
        "DYLIB_ARCHS" if args[1].endswith(".dylib") else "ARCHS", "arm64 x86_64"
    )
    if os.environ.get("LIPO_FAILURE") == args[0]:
        sys.exit(75)
    print(architectures if args[0] == "-archs"
          else "Architectures in the fat file: " + architectures)
elif tool == "python3":
    if args[0] == ".github/scripts/source_version.py":
        assert args == [".github/scripts/source_version.py", "--verify-bundle",
                        os.environ["BUNDLE_PATH"]], args
        os.execv(os.environ["REAL_PYTHON"], [os.environ["REAL_PYTHON"], *args])
    else:
        assert args[0] == ".github/scripts/release.py", args
        assert args[1:4] == [
            os.environ["RELEASE_COMMAND"], "--sha", os.environ["SELECTED_SHA"]
        ], args
        assert os.environ["GH_TOKEN"] == "fixture-token"
        if args[1] == "publish":
            assert args[4:] == [
                f"Kana-{os.environ['SOURCE_VERSION']}.zip",
                f"Kana-{os.environ['SOURCE_VERSION']}.dmg"
            ], args
            assert all(Path(path).is_file() for path in args[4:])
        else:
            assert len(args) == 4, args
elif tool == "security":
    assert args == ["find-identity", "-v", "-p", "codesigning", os.environ["KEYCHAIN_PATH"]]
    if os.environ.get("SIGN_MODE") != "missing-identity":
        print('1) FAKE "Developer ID Application: Fixture (TEST)"')
elif tool == "codesign":
    verify = args[0] == "--verify"
    expected = (["--verify", "--deep", "--strict", "--verbose=2"] if verify else
                ["--verbose", "--deep", "--timestamp", "--force", "--options=runtime",
                 "--sign", "Developer ID Application: Fixture (TEST)"])
    assert args == expected + [os.environ["BUNDLE_PATH"]], args
    if os.environ.get("SIGN_MODE") == ("verify" if verify else "sign"):
        sys.exit(76)
elif tool in ("ditto", "hdiutil"):
    assert bundle.is_dir()
    expected = (["-c", "-k", "--keepParent", os.environ["BUNDLE_PATH"]] if tool == "ditto"
                else ["create", "-format", "UDBZ", "-volname", "Kana",
                      "-srcfolder", os.environ["BUNDLE_PATH"]])
    assert args[:-1] == expected, args
    if os.environ.get("PACKAGE_FAILURE") == tool:
        sys.exit(77)
    Path(args[-1]).write_bytes(b"stub archive")
elif tool == "xcrun":
    scenario = os.environ.get("NOTARY_MODE", "accepted")
    if args[:2] == ["notarytool", "submit"]:
        assert args[3:] == [
            "--keychain-profile", "notarytool-profile", "--keychain",
            os.environ["KEYCHAIN_PATH"], "--wait", "--output-format", "json"
        ], args
        assert Path(args[2]).is_file()
        second = args[2].endswith(".dmg")
        status = "Invalid" if (
            scenario == "invalid" or (scenario == "second-invalid" and second)
        ) else "Accepted"
        if scenario == "malformed":
            print("this is not JSON")
        else:
            print(json.dumps({"id": "submission-dmg" if second else "submission-zip",
                              "status": status}))
        if scenario in ("transport", "accepted-nonzero") or (
            scenario == "second-transport" and second
        ):
            sys.exit(71)
    elif args[:2] == ["notarytool", "log"]:
        assert args[3:] == ["--keychain-profile", "notarytool-profile",
                            "--keychain", os.environ["KEYCHAIN_PATH"]], args
        sys.exit(72)
    elif args[:2] == ["stapler", "staple"]:
        assert len(args) == 3 and args[2].endswith(".dmg"), args
        if scenario == "staple":
            sys.exit(73)
    else:
        raise AssertionError(args)
elif tool == "plutil":
    assert args[0] == "-extract" and args[2:] == ["raw", "-o", "-", "-"], args
    try:
        value = json.load(sys.stdin)[args[1]]
        assert isinstance(value, str) and value
        print(value)
    except (ValueError, KeyError, AssertionError):
        sys.exit(74)
else:
    raise AssertionError("Unexpected tool: " + tool)
'''


class NativeShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".native-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in (*source.SOURCE_PATHS, Path(".github/scripts/source_version.py")):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        self.version = source.read(ROOT)
        self.assertEqual(source.read(self.root), self.version)
        self.source_bytes = {path: (self.root / path).read_bytes()
                             for path in source.SOURCE_PATHS}
        major, minor, patch = map(int, self.version.split("."))
        self.stale = f"{major}.{minor}.{patch + 1}"
        self.relative_bundle = "test/Plugins/Kana.bundle"
        self.bundle = self.root / self.relative_bundle
        shutil.copytree(ROOT / self.relative_bundle, self.bundle)
        self.contents = self.bundle / "Contents"
        self.log = self.root / "calls.jsonl"
        self.env_file = self.root / "github-env"
        self.env_file.touch()
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        for name in ("xcodebuild", "lipo", "python3", "ditto", "hdiutil", "xcrun",
                     "plutil", "security", "codesign"):
            executable = self.bin / name
            executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent(STUB))
            executable.chmod(0o755)
        # No fallback to installed Apple/native tools is possible.
        for name in ("rm", "ls", "grep", "head", "sed", "mkdir", "cp", "sort"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (self.bin / name).symlink_to(executable)
        self.env = {
            "PATH": str(self.bin), "CALL_LOG": str(self.log),
            "REAL_PYTHON": sys.executable, "PYTHONDONTWRITEBYTECODE": "1",
            "SOURCE_VERSION": self.version, "STALE_VERSION": self.stale,
            "BUNDLE_PATH": self.relative_bundle,
            "KEYCHAIN_PATH": str(self.root / "fake.keychain-db"),
            "GITHUB_ENV": str(self.env_file), "GH_TOKEN": "fixture-token",
            "SELECTED_SHA": "a" * 40, "RELEASE_COMMAND": "publish",
        }
        self.seed()

    def seed(self):
        self.write("MacOS/dependency.dylib", b"preserved runtime dependency")
        generated = {
            "MacOS/Kana", "Info.plist",
            "Resources/English.lproj/InfoPlist.strings", "_CodeSignature/CodeResources",
        }
        self.preserved = {
            str(path.relative_to(self.contents)): path.read_bytes()
            for path in self.contents.rglob("*")
            if path.is_file() and str(path.relative_to(self.contents)) not in generated
        }
        for relative in generated:
            self.write(relative, b"stale build output")
        for relative in ("Default/stale", "Kana.build/stale"):
            path = self.bundle.parent / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"stale intermediate")

    def write(self, relative, data):
        path = self.contents / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run_step(self, name, **env):
        script = step(name)
        values = {
            "env.PRODUCT_NAME": "Kana", "env.BASE_DIR": "test",
            "env.MACOS_DEPLOYMENT_TARGET": "11.5",
            "needs.version.outputs.version": self.version,
        }
        for key, value in values.items():
            script = script.replace("${{ " + key + " }}", value)
        self.assertNotIn("${{", script)
        return subprocess.run(
            ["/bin/bash", "-c", script], cwd=self.root, env={**self.env, **env},
            text=True, capture_output=True, timeout=30,
        )

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def calls(self, tool):
        if not self.log.exists():
            return []
        return [call[1:] for line in self.log.read_text().splitlines()
                if (call := json.loads(line))[0] == tool]

    def build(self, **env):
        self.assert_ok(self.run_step("build macOS plugin (universal)", **env))

    def snapshot(self):
        return {path.relative_to(self.bundle): path.read_bytes()
                for path in self.bundle.rglob("*") if path.is_file()}

    def test_preflight_executes_the_selected_sha_helper(self):
        self.assert_ok(self.run_step(
            "validate source and publication availability", RELEASE_COMMAND="preflight"
        ))
        self.assertEqual(self.calls("python3"), [[
            ".github/scripts/release.py", "preflight", "--sha", self.env["SELECTED_SHA"],
        ]])

    def test_fresh_universal_build_preserves_resources_windows_and_dependencies(self):
        self.build()
        self.assertEqual((self.contents / "MacOS/Kana").read_bytes(), b"rebuilt-universal")
        for relative, data in self.preserved.items():
            self.assertEqual((self.contents / relative).read_bytes(), data, relative)
        for path in (self.contents / "_CodeSignature", self.bundle.parent / "Default",
                     self.bundle.parent / "Kana.build"):
            self.assertFalse(path.exists())
        for path, data in self.source_bytes.items():
            self.assertEqual((self.root / path).read_bytes(), data, str(path))
        source.verify_bundle(self.bundle, self.root)
        self.assert_ok(self.run_step("verify universal binary"))
        self.assertEqual(len(self.calls("python3")), 1)
        self.assertEqual(len(self.calls("lipo")), 4)
        self.assertEqual(self.calls("xcodebuild"), [[
            "-project", "Kana.xcodeproj", "-target", "Kana",
            "-configuration", "Default", "ARCHS=arm64 x86_64", "ONLY_ACTIVE_ARCH=NO",
            "MACOSX_DEPLOYMENT_TARGET=11.5", "CODE_SIGNING_ALLOWED=NO",
            f"CONFIGURATION_BUILD_DIR={self.root}/test/Plugins", "build",
        ]])

    def test_build_failure_is_not_swallowed(self):
        result = self.run_step("build macOS plugin (universal)", BUILD_MODE="failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.contents / "MacOS/Kana").exists())

    def test_cleanup_error_aborts_before_xcodebuild(self):
        executable = self.bin / "rm"
        executable.unlink()
        executable.write_text("#!/bin/sh\nexit 79\n")
        executable.chmod(0o755)
        self.assertNotEqual(self.run_step("build macOS plugin (universal)").returncode, 0)
        self.assertEqual(self.calls("xcodebuild"), [])

    def test_missing_rebuilt_binary_is_rejected(self):
        self.build(BUILD_MODE="missing-binary")
        result = self.run_step("verify universal binary")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected binary not found", result.stdout)
        self.assertEqual(self.calls("lipo"), [])
        self.assertEqual(self.calls("python3"), [])

    def test_missing_or_stale_rebuilt_metadata_is_rejected(self):
        for mode in ("missing-plist", "missing-localized", "stale-plist",
                     "stale-build-version", "stale-localized"):
            with self.subTest(mode=mode):
                self.build(BUILD_MODE=mode)
                result = self.run_step("verify universal binary")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FileNotFoundError" if mode.startswith("missing")
                              else "differs from selected source", result.stderr)

    def test_exact_universal_architectures_are_required_for_binary_and_dylibs(self):
        self.build()
        for variable in ("ARCHS", "DYLIB_ARCHS"):
            for architectures in ("arm64", "x86_64", "arm64e x86_64",
                                  "arm64 x86_64h", "arm64 x86_64 i386",
                                  "arm64 x86_64 arm64e", ""):
                with self.subTest(variable=variable, architectures=architectures):
                    self.log.unlink(missing_ok=True)
                    result = self.run_step("verify universal binary",
                                           **{variable: architectures})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.calls("python3"), [])
        self.assert_ok(self.run_step("verify universal binary",
                                     ARCHS="x86_64 arm64", DYLIB_ARCHS="x86_64 arm64"))

    def test_lipo_errors_fail_closed(self):
        self.build()
        for operation in ("-info", "-archs"):
            with self.subTest(operation=operation):
                result = self.run_step("verify universal binary", LIPO_FAILURE=operation)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls("python3"), [])

    def test_manifest_and_constants_resource_gates(self):
        self.build()
        shutil.copyfile(ROOT / "constants.xlf", self.root / "constants.xlf")
        for relative in ("Resources/manifest.json", "Resources/constants.xlf"):
            with self.subTest(relative=relative):
                path = self.contents / relative
                data = path.read_bytes()
                path.unlink()
                self.assertNotEqual(self.run_step("verify universal binary").returncode, 0)
                self.assertEqual(self.calls("python3"), [])
                path.write_bytes(data)

    def test_compiled_localizations_are_checked_against_live_source(self):
        self.build()
        values = dict(re.findall(
            r'(?m)^(\w+)\s*=\s*"([^"]*)";',
            source.text(self.root / source.LOCALIZED),
        ))
        self.assertEqual(values["CFBundleShortVersionString"], self.version)
        for serialization in (plistlib.FMT_BINARY, plistlib.FMT_XML):
            with self.subTest(serialization=serialization):
                self.write("Resources/English.lproj/InfoPlist.strings",
                           plistlib.dumps(values, fmt=serialization))
                self.assert_ok(self.run_step("verify universal binary"))
                for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
                    stale = {**values, key: values[key].replace(self.version, self.stale)}
                    self.write("Resources/English.lproj/InfoPlist.strings",
                               plistlib.dumps(stale, fmt=serialization))
                    result = self.run_step("verify universal binary")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("differs from selected source", result.stderr)

    def test_exact_downloaded_artifact_rejects_missing_empty_and_nested_stale(self):
        before = self.snapshot()
        stale = self.root / "winbuild/aaa-stale/Kana.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"stale recursive match")
        artifact = self.root / "winbuild/Kana.4DX"
        for data in (None, b""):
            if data is not None:
                artifact.write_bytes(data)
            result = self.run_step("merge Windows binaries into the bundle")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact artifact path", result.stdout)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.env_file.read_text(), "")
        artifact.write_bytes(b"fresh selected-source Windows binary\x00\xff")
        self.assert_ok(self.run_step("merge Windows binaries into the bundle"))
        self.assertEqual(self.snapshot(), {
            **before, Path("Contents/Windows64/Kana.4DX"): artifact.read_bytes(),
        })
        self.assertEqual(self.env_file.read_text(), f"BUNDLE_PATH={self.relative_bundle}\n")
        self.assertEqual(stale.read_bytes(), b"stale recursive match")
        self.assertFalse(self.log.exists())

    def test_signing_requires_identity_sign_and_strict_verification(self):
        self.assert_ok(self.run_step("codesign"))
        self.assertEqual(len(self.calls("codesign")), 2)
        for scenario, count in (("missing-identity", 0), ("sign", 1), ("verify", 2)):
            with self.subTest(scenario=scenario):
                self.log.unlink()
                self.assertNotEqual(self.run_step("codesign", SIGN_MODE=scenario).returncode, 0)
                self.assertEqual(len(self.calls("codesign")), count)
                self.assertEqual(self.calls("ditto"), [])
                self.assertEqual(self.calls("xcrun"), [])

    def package_calls(self, submissions, staple=False, diagnostic=None):
        zip_path = f"Kana-{self.version}.zip"
        dmg_path = f"Kana-{self.version}.dmg"
        calls = self.calls("xcrun")
        self.assertEqual([call[2] for call in calls
                          if call[:2] == ["notarytool", "submit"]],
                         [zip_path, dmg_path][:submissions])
        self.assertEqual([call for call in calls if call[:2] == ["stapler", "staple"]],
                         [["stapler", "staple", dmg_path]] if staple else [])
        self.assertEqual([call[2] for call in calls if call[:2] == ["notarytool", "log"]],
                         [diagnostic] if diagnostic else [])

    def test_both_accepted_then_staple_exports_exact_versioned_paths(self):
        self.assert_ok(self.run_step("package, notarize & staple"))
        self.package_calls(2, staple=True)
        self.assertEqual(len(self.calls("ditto")), 1)
        self.assertEqual(len(self.calls("hdiutil")), 1)
        self.assertEqual(self.env_file.read_text().splitlines(), [
            f"ZIP_PATH=Kana-{self.version}.zip", f"DMG_PATH=Kana-{self.version}.dmg",
        ])

    def test_notary_and_staple_failures_never_export_publish_paths(self):
        for mode, submissions, staple, diagnostic in (
            ("invalid", 1, False, "submission-zip"),
            ("transport", 1, False, None),
            ("accepted-nonzero", 1, False, None),
            ("malformed", 1, False, None),
            ("second-invalid", 2, False, "submission-dmg"),
            ("second-transport", 2, False, None),
            ("staple", 2, True, None),
        ):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                result = self.run_step("package, notarize & staple", NOTARY_MODE=mode)
                self.assertNotEqual(result.returncode, 0)
                self.package_calls(submissions, staple, diagnostic)
                self.assertEqual(self.env_file.read_text(), "")

    def test_archive_failures_block_notarization(self):
        for tool in ("ditto", "hdiutil"):
            with self.subTest(tool=tool):
                self.log.unlink(missing_ok=True)
                result = self.run_step("package, notarize & staple", PACKAGE_FAILURE=tool)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls("xcrun"), [])
                self.assertEqual(self.env_file.read_text(), "")

    def test_end_to_end_stubbed_gate_order_before_publication(self):
        artifact = self.root / "winbuild/Kana.4DX"
        artifact.parent.mkdir()
        artifact.write_bytes(b"fresh Windows artifact")
        for name in ("check prebuilt libraries", "build macOS plugin (universal)",
                     "verify universal binary", "merge Windows binaries into the bundle",
                     "codesign", "package, notarize & staple"):
            self.assert_ok(self.run_step(name))
        exports = dict(line.split("=", 1) for line in self.env_file.read_text().splitlines())
        self.assert_ok(self.run_step("create GitHub Release", **exports))
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(calls[-2][0:3], ["xcrun", "stapler", "staple"])
        self.assertEqual(calls[-1], [
            "python3", ".github/scripts/release.py", "publish", "--sha",
            self.env["SELECTED_SHA"], f"Kana-{self.version}.zip", f"Kana-{self.version}.dmg",
        ])
        for path, data in self.source_bytes.items():
            self.assertEqual((self.root / path).read_bytes(), data, str(path))


class WindowsShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".native-windows-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "test/Plugins/Kana.bundle"
        shutil.copytree(ROOT / "test/Plugins/Kana.bundle", self.bundle)
        self.destination = self.bundle / "Contents/Windows64/Kana.4DX"
        self.output = self.root / "test/plugins/Kana.bundle/contents/windows64/Kana.4DX"
        self.preserved = {path.relative_to(self.bundle): path.read_bytes()
                          for path in self.bundle.rglob("*")
                          if path.is_file() and path != self.destination}
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        self.log = self.root / "unexpected-native-calls"
        for name in ("msbuild", "xcodebuild", "lipo", "codesign", "security",
                     "xcrun", "ditto", "hdiutil", "4D", "gh"):
            executable = self.bin / name
            executable.write_text(
                f"#!{sys.executable}\nimport os, sys\nfrom pathlib import Path\n"
                "Path(os.environ['CALL_LOG']).write_text(sys.argv[0])\nsys.exit(99)\n"
            )
            executable.chmod(0o755)
        self.env = {"PATH": str(self.bin), "CALL_LOG": str(self.log),
                    "PYTHONDONTWRITEBYTECODE": "1"}
        self.pwsh = shutil.which("pwsh")
        self.assertIsNotNone(self.pwsh, "PowerShell is required for native tests")

    def run_step(self, name, prelude="", postlude=""):
        script = step(name)
        for key, value in (("PRODUCT_NAME", "Kana"), ("BASE_DIR", "test")):
            script = script.replace("${{ env." + key + " }}", value)
        self.assertNotIn("${{", script)
        result = subprocess.run(
            [self.pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
             "$ErrorActionPreference = 'Stop'\n" + prelude + "\n" + script + "\n" + postlude],
            cwd=self.root, env=self.env, text=True, capture_output=True, timeout=30,
        )
        self.assertFalse(self.log.exists(), "A native operation was attempted")
        return result

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_preserved(self):
        for relative, data in self.preserved.items():
            self.assertEqual((self.bundle / relative).read_bytes(), data, str(relative))

    def clean(self):
        for relative in ("test/Plugins/Default/stale.4DX", "Objs/Release/stale.obj"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"stale intermediate")
        self.assert_ok(self.run_step("clean stale outputs"))
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.root / "test/Plugins/Default").exists())
        self.assertFalse((self.root / "Objs").exists())
        self.assert_preserved()

    def test_cleanup_accepts_already_missing_outputs(self):
        self.clean()
        self.assert_ok(self.run_step("clean stale outputs"))
        self.assert_preserved()

    def test_cleanup_removal_and_discovery_errors_abort(self):
        for cmdlet in ("Remove-Item", "Test-Path"):
            for failing in ("test/Plugins/Kana.bundle/Contents/Windows64/Kana.4DX",
                            "test/Plugins/Default", "Objs"):
                with self.subTest(cmdlet=cmdlet, failing=failing):
                    self.destination.parent.mkdir(parents=True, exist_ok=True)
                    self.destination.write_bytes(b"stale binary")
                    for relative in ("test/Plugins/Default/stale", "Objs/stale"):
                        path = self.root / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b"stale intermediate")
                    mock = r'''
function CMDLET {
    [CmdletBinding()]
    param([string]$LiteralPath, [switch]$Recurse, [switch]$Force)
    if ($LiteralPath -eq 'FAILING_PATH') {
        Write-Error "mock filesystem denied"
        return
    }
    Microsoft.PowerShell.Management\CMDLET @PSBoundParameters
}
'''.replace("CMDLET", cmdlet).replace("FAILING_PATH", failing)
                    result = self.run_step("clean stale outputs", prelude=mock,
                                           postlude="'yes' > cleanup-succeeded")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("mock filesystem denied", result.stdout + result.stderr)
                    self.assertTrue((self.root / failing).exists())
                    self.assertFalse((self.root / "cleanup-succeeded").exists())
                    self.assert_preserved()

    def test_cleanup_and_exact_msbuild_output_normalization(self):
        self.clean()
        stale = self.root / "test/aaa-stale/Kana.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"wrong recursive first match")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"mock rebuilt Release x64")
        self.assert_ok(self.run_step("normalize windows output to canonical case"))
        self.assertEqual(self.destination.read_bytes(), b"mock rebuilt Release x64")
        self.assertEqual(self.output.read_bytes(), b"mock rebuilt Release x64")
        self.assertEqual(stale.read_bytes(), b"wrong recursive first match")
        self.assert_preserved()

    def test_missing_exact_output_rejects_recursive_stale_match(self):
        self.clean()
        stale = self.root / "test/aaa-stale/Kana.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"wrong recursive first match")
        result = self.run_step("normalize windows output to canonical case")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Windows binary missing at exact MSBuild output",
                      result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertEqual(stale.read_bytes(), b"wrong recursive first match")
        self.assert_preserved()

    def test_same_physical_path_skips_self_copy_on_case_insensitive_filesystem(self):
        self.clean()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"mock rebuilt Release x64")
        same_path = self.destination.exists() and os.path.samefile(
            self.output, self.destination
        )
        result = self.run_step("normalize windows output to canonical case")
        self.assert_ok(result)
        self.assertEqual("skipping copy." in result.stdout, same_path)
        self.assertEqual(self.destination.read_bytes(), b"mock rebuilt Release x64")
        self.assertEqual(os.path.samefile(self.output, self.destination), same_path)
        self.assert_preserved()


class NativeConfigurationTests(unittest.TestCase):
    def test_manual_immutable_serialized_publication_contract(self):
        self.assertRegex(WORKFLOW, r"(?m)^name: Build$")
        self.assertRegex(WORKFLOW, r"(?m)^on:\n  workflow_dispatch:\n\n")
        self.assertNotIn("inputs:", WORKFLOW)
        self.assertIn("group: release-publication\n  cancel-in-progress: false", WORKFLOW)
        self.assertEqual(re.findall(r"ref: (.+)", WORKFLOW), ["${{ github.sha }}"] * 3)
        self.assertEqual(WORKFLOW.count("SELECTED_SHA: ${{ github.sha }}"), 2)
        self.assertEqual(WORKFLOW.count("GH_TOKEN: ${{ github.token }}"), 2)
        self.assertIn("needs: [version, build-windows]", WORKFLOW)
        self.assertIn("needs: version", WORKFLOW)
        self.assertNotIn("softprops/", WORKFLOW)
        self.assertNotRegex(WORKFLOW, r"(?m)^\s+if:")
        self.assertNotIn("continue-on-error", WORKFLOW)
        self.assertIn("tag: ${{ steps.set.outputs.tag }}", WORKFLOW)
        self.assertIn("version: ${{ steps.set.outputs.version }}", WORKFLOW)
        self.assertLess(WORKFLOW.index("ref: ${{ github.sha }}"),
                        WORKFLOW.index("- name: validate source"))
        names = [
            "build macOS plugin (universal)", "verify universal binary",
            "merge Windows binaries into the bundle", "codesign",
            "package, notarize & staple", "create GitHub Release",
        ]
        offsets = [WORKFLOW.index("- name: " + name) for name in names]
        self.assertEqual(offsets, sorted(offsets))
        self.assertTrue(WORKFLOW.rstrip().endswith(
            'python3 .github/scripts/release.py publish --sha "$SELECTED_SHA" "$ZIP_PATH" "$DMG_PATH"'
        ))
        self.assertIn("name: windows-binaries", WORKFLOW)
        self.assertIn("if-no-files-found: error", WORKFLOW)

    def test_windows_exact_output_matches_release_x64_project(self):
        project = ET.parse(ROOT / "Kana.vcxproj")
        namespace = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        condition = "'$(Configuration)|$(Platform)'=='Release|x64'"
        outdirs = [node.text for node in project.findall(".//m:OutDir", namespace)
                   if node.get("Condition") == condition]
        extensions = [node.text for node in project.findall(".//m:TargetExt", namespace)
                      if node.get("Condition") == condition]
        self.assertEqual(len(outdirs), 1)
        self.assertEqual(extensions, [".4DX"])
        actual = (outdirs[0].replace("$(ProjectDir)", "")
                  .replace("$(ProjectName)", "Kana").replace("\\", "/")
                  + "Kana" + extensions[0])
        normalize = step("normalize windows output to canonical case")
        match = re.search(r'^\$source = "([^"]+)"$', normalize, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(actual, match[1].replace("$base", "test").replace("$product", "Kana"))
        self.assertNotIn("-Recurse", normalize)
        self.assertNotIn("SilentlyContinue", normalize)
        self.assertIn("$sourceResolved -ieq $destResolved", normalize)
        self.assertIn("Copy-Item -LiteralPath $source $destination -Force", normalize)
        self.assertIn("/p:Configuration=Release /p:Platform=x64", step("build x64"))
        self.assertIn("/p:PlatformToolset=v143 /p:WindowsTargetPlatformVersion=10.0",
                      step("build x64"))
        self.assertEqual({node.text for node in project.findall(".//m:PlatformToolset", namespace)},
                         {"v140"})
        self.assertEqual({node.get("Include") for node in
                          project.findall(".//m:ProjectConfiguration", namespace)},
                         {"Debug|Win32", "Debug|x64", "Release|Win32", "Release|x64"})

    def test_original_macos_resources_settings_and_secrets(self):
        project = (ROOT / source.PROJECT).read_text()
        for setting, value, count in (
            ("SDKROOT", "macosx", 6), ("MACOSX_DEPLOYMENT_TARGET", "11.5", 6),
            ("CLANG_CXX_LIBRARY", '"libc++"', 6), ("INFOPLIST_FILE", "Info.plist", 3),
            ("WRAPPER_EXTENSION", "bundle", 3),
        ):
            self.assertEqual(len(re.findall(
                rf"(?m)^\s*{setting} = {re.escape(value)};", project
            )), count)
        for name in ("Default", "Development", "Deployment"):
            self.assertEqual(len(re.findall(rf"(?m)^\s*name = {name};", project)), 2)
        for resource in ("manifest.json in CopyFiles", "constants.xlf in CopyFiles",
                         "Cocoa.framework in Frameworks", "InfoPlist.strings in Resources"):
            self.assertIn(resource, project)
        self.assertEqual(set(re.findall(r"\$\{\{ secrets\.([A-Z_]+) \}\}", WORKFLOW)), {
            "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
            "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
            "NOTARYTOOL_PASSWORD",
        })
        self.assertIn("runs-on: windows-latest", WORKFLOW)
        self.assertIn("runs-on: macos-latest", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
