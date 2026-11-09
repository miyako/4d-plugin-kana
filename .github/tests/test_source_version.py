import importlib.util
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("source_version", ROOT / ".github/scripts/source_version.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)

LOCALIZED_SHORT = re.compile(
    r'(?m)^([ \t]*CFBundleShortVersionString[ \t]*=[ \t]*")([^"]*)("[ \t]*;[ \t]*)$'
)
LOCALIZED_INFO = re.compile(
    r'(?m)^([ \t]*CFBundleGetInfoString[ \t]*=[ \t]*"Kana version )'
    r'([^,"]*)(, Copyright 2021 miyako\."[ \t]*;[ \t]*)$'
)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".source-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.copy_source()
        self.current = source.read(self.root)
        major, minor, patch = map(int, self.current.split("."))
        self.drifted = f"{major + 1}.{minor}.{patch}"

    def copy_source(self):
        for path in source.SOURCE_PATHS:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, target)

    def plist(self, **values):
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        data.update(values)
        path.write_bytes(plistlib.dumps(data))

    def snapshot(self):
        return {path: (self.root / path).read_bytes() for path in source.SOURCE_PATHS}

    def assert_rejected(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            source.bump("patch", self.root)
        self.assertEqual(before, self.snapshot())

    def test_live_metadata_and_all_bump_modes(self):
        parts = list(map(int, self.current.split(".")))
        self.assertEqual(source.SETTING_COUNTS, {"MARKETING_VERSION": 6, "CURRENT_PROJECT_VERSION": 3})
        for mode, expected in (
            ("patch", [parts[0], parts[1], parts[2] + 1]),
            ("minor", [parts[0], parts[1] + 1, 0]),
            ("major", [parts[0] + 1, 0, 0]),
        ):
            with self.subTest(mode=mode):
                self.copy_source()
                expected = ".".join(map(str, expected))
                self.assertEqual(source.bump(mode, self.root), expected)
                self.assertEqual(source.read(self.root), expected)
                self.assertNotIn("CFBundleVersion",
                                 plistlib.loads((self.root / source.PLIST).read_bytes()))
                for key, count in source.SETTING_COUNTS.items():
                    self.assertEqual(source.text(self.root / source.PROJECT).count(
                        f"{key} = {expected};"), count)

    def test_stable_fixture_coordinated_contract(self):
        project = self.root / source.PROJECT
        project.write_text(
            "".join(f"{key} = 3.2.1;\n" * count
                    for key, count in source.SETTING_COUNTS.items())
        )
        self.plist(CFBundleShortVersionString="3.2.1", CFBundleVersion="3.2.1")
        (self.root / source.LOCALIZED).write_text(
            'CFBundleName = "Kana";\nCFBundleShortVersionString = "3.2.1";\n'
            'CFBundleGetInfoString = "Kana version 3.2.1, Copyright 2021 miyako.";\n',
            encoding="utf-8-sig",
        )
        self.assertEqual(source.read(self.root), "3.2.1")
        self.assertEqual(source.bump("minor", self.root), "3.3.0")
        self.assertEqual(project.read_text().count("CURRENT_PROJECT_VERSION = 3.3.0;"),
                         source.SETTING_COUNTS["CURRENT_PROJECT_VERSION"])
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())["CFBundleVersion"],
                         "3.3.0")
        self.plist(CFBundleShortVersionString="$(CURRENT_PROJECT_VERSION)")
        self.assertEqual(source.read(self.root), "3.3.0")

    def test_invalid_missing_extra_and_drifted_settings(self):
        path = self.root / source.PROJECT
        original = source.text(path)
        for key, total in source.SETTING_COUNTS.items():
            for bad in ("1.2", "14.3", "77", "v1.2.3", "01.2.3", "1.2.3-beta",
                        "$(UNKNOWN)", "", self.drifted,
                        "$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}"):
                for count in (1, total):
                    with self.subTest(key=key, bad=bad, count=count):
                        path.write_text(original.replace(
                            f"{key} = {self.current};", f"{key} = {bad};", count))
                        self.assert_rejected()
            path.write_text(original.replace(f"{key} = {self.current};", "", 1))
            self.assert_rejected()
            path.write_text(original + f"\n{key} = {self.current};\n")
            self.assert_rejected()
        for reference in source.REFERENCES:
            path.write_text(original.replace(
                f"MARKETING_VERSION = {self.current};", f'MARKETING_VERSION = "{reference}";'))
            self.assert_rejected()

    def test_plist_invalid_missing_and_drift(self):
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            for value in ("$(UNKNOWN)", "$(PRODUCT_NAME)", "", "invalid", 123,
                          self.drifted, "1.2", "14.3", "7", "01.2.3", "v1.2.3"):
                with self.subTest(key=key, value=value):
                    self.copy_source()
                    self.plist(**{key: value})
                    self.assert_rejected()
        self.copy_source()
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        del data["CFBundleShortVersionString"]
        path.write_bytes(plistlib.dumps(data))
        self.assert_rejected()
        path.write_bytes(plistlib.dumps([]))
        self.assert_rejected()

    def test_malformed_extra_settings_and_quoted_localized_duplicates_rejected(self):
        project = self.root / source.PROJECT
        original = source.text(project)
        for key, count in source.SETTING_COUNTS.items():
            project.write_text(original + f"\n{key} = {self.current}\n")
            self.assert_rejected()
            project.write_text(original + f'\n"{key}" = {self.current};\n')
            self.assert_rejected()
        self.copy_source()
        localized = self.root / source.LOCALIZED
        original = source.text(localized)
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            localized.write_text(original + f'\n"{key}" = "{self.current}";\n')
            self.assert_rejected()

    def test_supported_references_preserved_and_literals_co_bumped(self):
        for reference in source.REFERENCES:
            for marketing_ref in ("$(MARKETING_VERSION)", "${MARKETING_VERSION}"):
                with self.subTest(reference=reference, marketing_ref=marketing_ref):
                    self.copy_source()
                    self.plist(CFBundleShortVersionString=reference, CFBundleVersion=reference)
                    path = self.root / source.PROJECT
                    path.write_text(source.SETTING.sub(
                        lambda m: f'{m[1]}"{marketing_ref}"{m[4]}'
                        if m[2] == "CURRENT_PROJECT_VERSION" else m[0], source.text(path)))
                    before = self.snapshot()
                    new = source.bump("patch", self.root)
                    self.assertEqual(source.read(self.root), new)
                    for name, original in before.items():
                        self.assertEqual((self.root / name).read_bytes(),
                                         original.replace(self.current.encode(), new.encode()))
        self.copy_source()
        self.plist(CFBundleVersion=self.current)
        new = source.bump("minor", self.root)
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())["CFBundleVersion"],
                         new)

    def test_build_reference_with_drift_is_rejected_before_any_write(self):
        self.plist(CFBundleShortVersionString="$(CURRENT_PROJECT_VERSION)",
                   CFBundleVersion="${CURRENT_PROJECT_VERSION}")
        project = self.root / source.PROJECT
        project.write_text(source.text(project).replace(
            f"CURRENT_PROJECT_VERSION = {self.current};", "CURRENT_PROJECT_VERSION = 77;"))
        self.assert_rejected()

    def test_quoted_localized_keys_and_inline_duplicates(self):
        path = self.root / source.LOCALIZED
        original = source.text(path)
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            for quoted in (False, True):
                with self.subTest(key=key, quoted=quoted):
                    name = f'"{key}"' if quoted else key
                    path.write_text(original + f'CFBundleOther = "other"; {name} = "bad";\n')
                    self.assert_rejected()
        quoted = original
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            quoted = quoted.replace(key + " =", f'"{key}" =')
        quoted += '// CFBundleShortVersionString = "not an assignment";\n'
        quoted += '/* "CFBundleGetInfoString" = "not an assignment"; */\n'
        path.write_text(quoted)
        new = source.bump("patch", self.root)
        self.assertEqual(path.read_bytes(), quoted.replace(self.current, new).encode())

    def test_inline_quoted_and_unquoted_localized_assignments(self):
        for quoted in (False, True):
            with self.subTest(quoted=quoted):
                self.copy_source()
                path = self.root / source.LOCALIZED
                original = source.text(path)
                if quoted:
                    for key in ("CFBundleName", "CFBundleShortVersionString",
                                "CFBundleGetInfoString"):
                        original = original.replace(key + " =", f'"{key}" =')
                original = original.replace("\n", " ")
                path.write_bytes(b"\xef\xbb\xbf" + original.encode())
                before = path.read_bytes()
                new = source.bump("patch", self.root)
                self.assertEqual(path.read_bytes(),
                                 before.replace(self.current.encode(), new.encode()))

    def test_unrelated_identical_version_bytes_are_preserved(self):
        project = self.root / source.PROJECT
        localized = self.root / source.LOCALIZED
        plist = self.root / source.PLIST
        with project.open("ab") as stream:
            stream.write(f'\n// unrelated version {self.current}\n'.encode())
        with localized.open("ab") as stream:
            stream.write(f'\rOtherVersion = "{self.current}";\r'
                         f'// CFBundleShortVersionString = "{self.current}";\r'.encode())
        self.plist(UnrelatedVersion=self.current, CFBundleVersion=self.current)
        new = source.bump("minor", self.root)
        self.assertIn(f"// unrelated version {self.current}", source.text(project))
        self.assertIn(f'OtherVersion = "{self.current}";', source.text(localized))
        self.assertIn(f'// CFBundleShortVersionString = "{self.current}";',
                      source.text(localized))
        data = plistlib.loads(plist.read_bytes())
        self.assertEqual(data["UnrelatedVersion"], self.current)
        self.assertEqual(data["CFBundleVersion"], new)

    def test_actual_cr_only_localized_input_and_absent_build_version(self):
        original = (self.root / source.LOCALIZED).read_bytes()
        self.assertIn(b"\r", original)
        self.assertNotIn(b"\n", original)
        plist = self.root / source.PLIST
        before = plist.read_bytes()
        self.assertNotIn("CFBundleVersion", plistlib.loads(before))
        self.assertEqual(plistlib.loads(before)["CFBundleShortVersionString"],
                         "$(MARKETING_VERSION)")
        new = source.bump("patch", self.root)
        self.assertEqual(plist.read_bytes(), before)
        self.assertEqual((self.root / source.LOCALIZED).read_bytes(),
                         original.replace(self.current.encode(), new.encode()))

    def test_malformed_localized_tokens_and_quoted_project_settings(self):
        localized = self.root / source.LOCALIZED
        original = source.text(localized)
        for suffix in ('CFBundleOther = "unterminated', '/* unterminated',
                       'CFBundleOther nonsense;', '"CFBundleOther" = 7;'):
            with self.subTest(suffix=suffix):
                localized.write_text(original + suffix)
                self.assert_rejected()
        self.copy_source()
        project = self.root / source.PROJECT
        original = source.text(project)
        for key in source.KEYS:
            for suffix in (f"{key} nonsense", f'"{key}" nonsense',
                           f'"{key}" = "{self.current}"'):
                with self.subTest(suffix=suffix):
                    project.write_text(original + "\n" + suffix + "\n")
                    self.assert_rejected()

    def test_duplicate_plist_keys_and_invalid_serialization_fail_closed(self):
        path = self.root / source.PLIST
        original = source.text(path)
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            for value in (self.current, self.drifted):
                with self.subTest(key=key, value=value):
                    self.copy_source()
                    if key == "CFBundleVersion":
                        self.plist(CFBundleVersion=self.current)
                    data = source.text(path)
                    path.write_text(data.replace(
                        "</dict>", f"<key>{key}</key><string>{value}</string>\n</dict>"))
                    self.assert_rejected()
        for malformed in (
            b"not a plist", original.replace("</dict>", "").encode(),
            original.replace("<string>$(MARKETING_VERSION)",
                             "<string>&#36;(MARKETING_VERSION)").encode(),
            plistlib.dumps(plistlib.loads(original.encode()), fmt=plistlib.FMT_BINARY),
        ):
            with self.subTest(serialization=malformed[:40]):
                self.copy_source()
                path.write_bytes(malformed)
                self.assert_rejected()

    def test_localized_validation(self):
        path = self.root / source.LOCALIZED
        original = source.text(path)
        for pattern in (LOCALIZED_SHORT, LOCALIZED_INFO):
            for bad in ("1.0", self.drifted, "invalid", "", "$(UNKNOWN)", "$(MARKETING_VERSION)",
                        "${CURRENT_PROJECT_VERSION}", "01.2.3", "1.2.3-beta"):
                with self.subTest(pattern=pattern.pattern, bad=bad):
                    path.write_text(pattern.sub(lambda m: f"{m[1]}{bad}{m[3]}", original))
                    self.assert_rejected()
            path.write_text(pattern.sub("", original))
            self.assert_rejected()
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            path.write_text(original.replace(key, "UnknownKey"))
            self.assert_rejected()
            path.write_text(original + f'\n{key} = "{self.current}";\n')
            self.assert_rejected()
        for bad in ("Other Product", "Copyright 2023", "Copyright 2021 someone"):
            path.write_text(original.replace(
                "Kana" if bad == "Other Product" else
                "Copyright 2021" if bad == "Copyright 2023" else "Copyright 2021 miyako", bad))
            self.assert_rejected()

    def test_missing_source_files_rejected_without_writes(self):
        for name in source.SOURCE_PATHS:
            self.copy_source()
            (self.root / name).unlink()
            before = {p: (self.root / p).read_bytes() for p in source.SOURCE_PATHS if p != name}
            with self.assertRaises(FileNotFoundError):
                source.bump("patch", self.root)
            self.assertEqual(before, {p: (self.root / p).read_bytes() for p in before})

    def test_byte_preserving_endings_bom_and_modes(self):
        for newline in ("\n", "\r", "\r\n", "mixed"):
            for bom in (b"", b"\xef\xbb\xbf"):
                with self.subTest(newline=newline, bom=bom):
                    self.copy_source()
                    originals = {}
                    for i, name in enumerate(source.SOURCE_PATHS):
                        path = self.root / name
                        lines = source.text(path).splitlines(keepends=True)
                        value = "".join(line.replace(
                            "\n", ("\r", "\r\n", "\n")[j % 3] if newline == "mixed" else newline
                        ) for j, line in enumerate(lines))
                        path.write_bytes(bom + value.encode())
                        path.chmod((0o755, 0o640, 0o644)[i])
                        originals[name] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                    new = source.bump("minor", self.root)
                    for name, (before, mode) in originals.items():
                        path = self.root / name
                        self.assertEqual(path.read_bytes(), before.replace(
                            self.current.encode(), new.encode()))
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)

    def test_whitespace_and_quotes_preserved(self):
        for quoted in (False, True):
            self.copy_source()
            path = self.root / source.PROJECT
            old = self.current.encode()
            value = b'"' + old + b'"' if quoted else old
            before = path.read_bytes()
            for key, count in source.SETTING_COUNTS.items():
                before = before.replace(key.encode() + b" = " + old + b";",
                                        key.encode() + b" \t= \t" + value + b" \t;")
            path.write_bytes(before)
            localized = self.root / source.LOCALIZED
            localized.write_bytes(localized.read_bytes().replace(b" = ", b" \t= \t")
                                  .replace(b'";', b'" \t; \t'))
            snapshots = self.snapshot()
            new = source.bump("patch", self.root)
            for name, original in snapshots.items():
                self.assertEqual((self.root / name).read_bytes(), original.replace(old, new.encode()))

    def test_prebuilt_4d_schema_and_dependency_files_ignored(self):
        excluded = (
            "test/Plugins/Kana.bundle/Contents/Info.plist",
            "test/Plugins/Kana.bundle/Contents/Resources/English.lproj/InfoPlist.strings",
            "test/Plugins/Kana.bundle/Contents/Resources/manifest.json",
            "test/Plugins/Kana.bundle/Contents/Resources/constants.xlf",
            "test/Plugins/Kana.bundle/Contents/QuickLook/Thumbnail.png",
            "test/Plugins/Kana.bundle/Contents/Windows64/Kana.4DX",
            "test/Project/test.4DProject", "test/Project/Sources/catalog.4DCatalog",
            "test/Project/Sources/Methods/test.4dm", "manifest.json", "constants.xlf",
            "constants.json", "4D Plugin API/4DPluginAPI.h", "4D Plugin API/Classes/C_TYPES.h",
            "Kana.vcxproj", "Kana.vcxproj.filters", "Kana.sln", "4DPlugin-Kana.h",
        )
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files"], check=True, capture_output=True, text=True
        ).stdout.splitlines()
        self.assertTrue(set(excluded).issubset(tracked))
        for name in excluded:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)
        before = {name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
                  for name in excluded}
        source.bump("major", self.root)
        self.assertEqual(before, {
            name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
            for name in excluded
        })

    def test_invalid_mode_and_cli_read_do_not_write(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            source.bump("other", self.root)
        output = subprocess.run(
            [sys.executable, str(ROOT / ".github/scripts/source_version.py")],
            cwd=self.root, check=True, capture_output=True, text=True,
        )
        self.assertEqual(output.stdout.strip(), self.current)
        self.assertEqual(before, self.snapshot())

    def test_built_plist_root_and_optional_build_key(self):
        contents = self.root / "built.bundle/Contents"
        localized = contents / "Resources/English.lproj/InfoPlist.strings"
        localized.parent.mkdir(parents=True)
        shutil.copy2(self.root / source.LOCALIZED, localized)
        built = contents / "Info.plist"
        built.write_bytes(plistlib.dumps({key: self.current if value in source.REFERENCES else value
                                          for key, value in plistlib.loads((self.root / source.PLIST).read_bytes()).items()}))
        source.verify_bundle(contents.parent, self.root)
        built.write_bytes(plistlib.dumps([]))
        with self.assertRaisesRegex(ValueError, "display version"):
            source.verify_bundle(contents.parent, self.root)
        self.plist(CFBundleVersion=self.current)
        built.write_bytes(plistlib.dumps({"CFBundleShortVersionString": self.current}))
        with self.assertRaisesRegex(ValueError, "build version"):
            source.verify_bundle(contents.parent, self.root)
        built.write_bytes(plistlib.dumps({key: self.current if value in source.REFERENCES else value
                                          for key, value in plistlib.loads((self.root / source.PLIST).read_bytes()).items()}))
        source.verify_bundle(contents.parent, self.root)


if __name__ == "__main__":
    unittest.main()
